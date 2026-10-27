"""
Multi-step login/registration workflow engine.

A "workflow" is a JSON array of steps (e.g. produced for --login-file /
--register-file in ptaccount). Each step names an action ("send_request", ...)
and a set of named regular expressions used to pull data out of that action's
result. Extracted values are merged into a shared variables dict and can be
referenced by later steps via {{name}} placeholders, and the full merged dict
is handed back to the caller so it can decide what the result means (e.g.
whether a login attempt succeeded).

Public functions:
    execute_workflow(workflow, variables, ptjsonlib, http_client) -> WorkflowResult
    execute_step(step, variables, ptjsonlib, http_client) -> StepResult
    send_request(step, variables, ptjsonlib, http_client) -> requests.Response
    get_data_from_email(email_config) -> str
    load_workflow(workflow_file) -> list
"""

import base64
import binascii
import email
import imaplib
import json
import os
import poplib
import re
import time
from dataclasses import dataclass
from email.header import decode_header
from typing import Optional
from urllib.parse import urlparse

from ptlibs.parsers.http_request_parser import HttpRequestParser

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class StepResult:
    variables: dict
    response: Optional[object]  # requests.Response for a "send_request" step


@dataclass
class WorkflowResult:
    variables: dict    # every value extracted along the way, keyed by regex name, from every step
    steps: list         # one StepResult per step, in order


def execute_workflow(workflow, variables: dict = None, ptjsonlib: object = None, http_client: object = None,
                      use_json: bool = False, method_override: Optional[str] = None,
                      extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None,
                      default_allow_redirects: Optional[bool] = None, email_config: Optional[dict] = None) -> WorkflowResult:
    """Load (if needed) and run every step of a workflow, in order.

    workflow is either the already-loaded step list (see load_workflow() - handing this
    in avoids re-reading/re-parsing the file on every call, e.g. once per credential
    attempt), or a workflow_file: a path to a JSON file, or the workflow JSON itself
    base64-encoded (--login-file/--register-file accept either).

    variables seeds the substitution dict for {{name}} placeholders (e.g.
    {"login": ..., "password": ...}).

    method_override/extra_headers/allow_redirects let a caller override this one run
    without altering the workflow template itself - e.g. a test that swaps the login
    request's HTTP method, or pins a specific Cookie value for the whole attempt.
    method_override/allow_redirects apply only to the *last* step (the one that
    actually submits the credentials/registration data) - earlier steps (a CSRF token
    fetch, etc.) always run with their own templated verb/redirect behavior.
    extra_headers applies to every step, since it represents state (e.g. a cookie) the
    caller already holds and a real client would present on every request.

    Redirect handling, highest precedence first (see send_request): an explicit
    allow_redirects override (last step only) > the step's own "redirect" key (any
    step) > default_allow_redirects, the ambient default such as a -r/--redirects
    switch (last step only) > the http client's own default. A step can thus pin its
    redirect behavior in the workflow file regardless of -r, while a caller that is
    specifically testing redirect behavior can still force it.

    Returns a WorkflowResult: .variables is every value extracted along the way (not
    just the last step's), and .steps is each step's own StepResult (including its raw
    response) for callers that need more than what regex extraction captured - e.g.
    cookies or redirect history from a specific step.
    """
    steps = load_workflow(workflow) if isinstance(workflow, str) else workflow
    variables = dict(variables or {})
    last_index = len(steps) - 1
    step_results = []

    for index, step in enumerate(steps):
        is_last = index == last_index
        result = execute_step(
            step, variables, ptjsonlib=ptjsonlib, http_client=http_client, use_json=use_json,
            method_override=method_override if is_last else None,
            extra_headers=extra_headers,
            allow_redirects=allow_redirects if is_last else None,
            default_allow_redirects=default_allow_redirects if is_last else None,
            email_config=email_config,
        )
        variables.update(result.variables)
        step_results.append(result)

    return WorkflowResult(variables=variables, steps=step_results)


def execute_step(step: dict, variables: dict, ptjsonlib: object = None, http_client: object = None,
                  use_json: bool = False, method_override: Optional[str] = None,
                  extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None,
                  default_allow_redirects: Optional[bool] = None, email_config: Optional[dict] = None) -> StepResult:
    """Run one workflow step and return the variables extracted from its result via step["regex"],
    plus (for a "send_request" step) the raw requests.Response, for callers that need to inspect
    it directly (status code, cookies, redirect history, ...) beyond what regex extraction covers.

    A pattern with a capturing group returns that group's value; a plain
    match-only pattern (no group) returns the full matched text - useful for
    presence checks like {"success": "Welcome back"}. Patterns that don't
    match are simply absent from the returned dict; a later {{name}} that
    references a missing variable is left untouched rather than substituted.

    method_override/extra_headers/allow_redirects only apply to a "send_request"
    step - see send_request() - and let a caller (e.g. a test that swaps the login
    request's HTTP method) override this one invocation without altering the
    workflow template itself.
    """
    action = step.get("action")

    if action == "send_request":
        response = send_request(step, variables, ptjsonlib=ptjsonlib, http_client=http_client, use_json=use_json,
                                 method_override=method_override, extra_headers=extra_headers, allow_redirects=allow_redirects,
                                 default_allow_redirects=default_allow_redirects)
        raw_text = _raw_response_text(response)
    elif action == "get_data_from_email":
        # No HTTP response - the "response" is the mailbox's most recent message, whose decoded
        # text the step's regex pulls data out of (e.g. a 2FA code mailed to the user).
        response = None
        raw_text = get_data_from_email(email_config)
    else:
        raise ValueError(f"Unknown workflow action: {action!r}")

    return StepResult(variables=_extract_variables(step.get("regex"), raw_text), response=response)


def send_request(step: dict, variables: dict, ptjsonlib: object = None, http_client: object = None,
                  use_json: bool = False, method_override: Optional[str] = None,
                  extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None,
                  default_allow_redirects: Optional[bool] = None):
    """Send the raw HTTP request described by a "send_request" step, with {{name}} placeholders
    in step["content"] filled in from variables, and return the resulting requests.Response.

    method_override, if given, replaces the parsed HTTP method (only the verb changes -
    the body/headers are still sent as templated). extra_headers, if given, is merged over
    the parsed headers (it wins on a name clash).

    Whether redirects are followed is decided, highest precedence first: an explicit
    allow_redirects override > the step's own "redirect" key (JSON bool, alongside
    "schema") > default_allow_redirects (the ambient default, e.g. a -r switch). When
    none of these is set, http_client.send_request's own default applies.
    """
    schema = step.get("schema", "https")
    content = substitute_variables(step["content"], variables)

    parser = HttpRequestParser(ptjsonlib, use_json=use_json)
    url, method, headers, data = parser.parse_http_request(content, scheme=schema)
    if extra_headers:
        headers = {**headers, **extra_headers}

    if allow_redirects is not None:
        effective_redirects = allow_redirects
    elif "redirect" in step:
        effective_redirects = bool(step["redirect"])
    else:
        effective_redirects = default_allow_redirects

    kwargs = {} if effective_redirects is None else {"allow_redirects": effective_redirects}
    return http_client.send_request(url=url, method=method_override or method, headers=headers, data=data or None, **kwargs)


_EMAIL_DEFAULT_PORTS = {"imap": 143, "imaps": 993, "pop3": 110, "pop3s": 995}


def get_data_from_email(email_config: Optional[dict], poll_timeout: float = 20.0,
                        poll_interval: float = 2.0) -> str:
    """Connect to a mailbox and return the decoded text (key headers + body) of its most recent
    message, so a workflow regex can pull a value out of it - e.g. a 2FA code mailed to the user.

    email_config is {"server": "[scheme://]host[:port]", "login": ..., "password": ...}; the
    scheme picks the protocol and TLS (imap/imaps/pop3/pop3s, default imap) and the port defaults
    per scheme. The mailbox is polled up to poll_timeout seconds for a message to appear (a 2FA
    mail usually lands a moment after the request that triggered it). Returns "" if none arrived
    in time, so a missing variable is simply absent rather than an error.

    Lives in ptlibs so other tools can reuse it, and is called by the "get_data_from_email"
    workflow action.
    """
    if not email_config or not email_config.get("server"):
        raise ValueError("a 'get_data_from_email' step needs --email-server, --email-login and --email-password")

    scheme, host, port = _parse_email_server(email_config["server"])
    login = email_config.get("login")
    password = email_config.get("password")

    deadline = time.time() + poll_timeout
    while True:
        raw = _fetch_last_message(scheme, host, port, login, password)
        if raw is not None:
            return _email_to_text(raw)
        if time.time() >= deadline:
            return ""
        time.sleep(poll_interval)


def _parse_email_server(server: str) -> tuple:
    if "://" not in server:
        server = "imap://" + server
    parsed = urlparse(server)
    scheme = (parsed.scheme or "imap").lower()
    if scheme not in _EMAIL_DEFAULT_PORTS:
        raise ValueError(f"unsupported email scheme {scheme!r} (use imap, imaps, pop3 or pop3s)")
    if not parsed.hostname:
        raise ValueError(f"could not parse host from --email-server {server!r}")
    return scheme, parsed.hostname, parsed.port or _EMAIL_DEFAULT_PORTS[scheme]


def _fetch_last_message(scheme: str, host: str, port: int, login: str, password: str):
    """Raw bytes of the mailbox's most recent message, or None if the mailbox is empty."""
    if scheme.startswith("imap"):
        return _fetch_last_imap(scheme, host, port, login, password)
    return _fetch_last_pop3(scheme, host, port, login, password)


def _fetch_last_imap(scheme, host, port, login, password):
    connection = (imaplib.IMAP4_SSL if scheme == "imaps" else imaplib.IMAP4)(host, port)
    try:
        connection.login(login, password)
        connection.select("INBOX")
        _, data = connection.search(None, "ALL")
        message_ids = data[0].split()
        if not message_ids:
            return None
        _, message_data = connection.fetch(message_ids[-1], "(RFC822)")
        for part in message_data:
            if isinstance(part, tuple):
                return part[1]
        return None
    finally:
        try:
            connection.logout()
        except Exception:
            pass


def _fetch_last_pop3(scheme, host, port, login, password):
    connection = (poplib.POP3_SSL if scheme == "pop3s" else poplib.POP3)(host, port, timeout=15)
    try:
        connection.user(login)
        connection.pass_(password)
        count = len(connection.list()[1])
        if count == 0:
            return None
        return b"\r\n".join(connection.retr(count)[1])
    finally:
        try:
            connection.quit()
        except Exception:
            pass


def _email_to_text(raw: bytes) -> str:
    """Flatten a raw RFC822 message into searchable text: a few key headers plus every decoded
    text/plain and text/html part (MIME, charset and transfer-encoding handled)."""
    message = email.message_from_bytes(raw)
    parts = [f"From: {_decode_mime_header(message.get('From', ''))}",
             f"Subject: {_decode_mime_header(message.get('Subject', ''))}",
             ""]
    for part in message.walk():
        if part.get_content_type() not in ("text/plain", "text/html") or part.get_filename():
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            parts.append(payload.decode(charset, errors="replace"))
        except LookupError:
            parts.append(payload.decode("utf-8", errors="replace"))
    return "\n".join(parts)


def _decode_mime_header(value: str) -> str:
    decoded = []
    for text, charset in decode_header(value or ""):
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def substitute_variables(text: str, variables: dict) -> str:
    """Replace every {{name}} in text with str(variables[name]); a name missing
    from variables is left as literal {{name}}."""
    def _replace(match: re.Match) -> str:
        name = match.group(1)
        return str(variables[name]) if name in variables else match.group(0)
    return _VAR_PATTERN.sub(_replace, text)


def load_workflow(workflow_file: str) -> list:
    """Load a workflow's step list from a file path or base64-encoded JSON (see execute_workflow)."""
    return json.loads(_load_text_or_base64(workflow_file))


def _load_text_or_base64(value: str) -> str:
    if os.path.isfile(value):
        with open(value, "r") as f:
            return f.read()
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError(f"'{value}' is neither an existing file nor valid base64-encoded content")


def _extract_variables(regex_map: dict, text: str) -> dict:
    extracted = {}
    for name, pattern in (regex_map or {}).items():
        match = re.search(pattern, text)
        if not match:
            continue
        extracted[name] = match.group(1) if match.groups() else match.group(0)
    return extracted


def _raw_response_text(response) -> str:
    """Reconstruct a raw-response-like text (status line + headers + body) so that
    regexes can target the status line or headers (e.g. Set-Cookie), not just the body.
    """
    status_line = f"HTTP/1.1 {getattr(response, 'status_code', '')} {getattr(response, 'reason', '') or ''}".rstrip()
    header_lines = "\n".join(f"{key}: {value}" for key, value in _response_header_items(response))
    body = getattr(response, "text", "") or ""
    return f"{status_line}\n{header_lines}\n\n{body}"


def _response_header_items(response) -> list:
    # response.headers (requests.structures.CaseInsensitiveDict) collapses repeated
    # headers - notably Set-Cookie - into one comma-joined value. response.raw.headers
    # is urllib3's HTTPHeaderDict, which preserves each occurrence separately, so a
    # regex against a single Set-Cookie value (e.g. a session id) still works when the
    # server sets more than one cookie.
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    if raw_headers is not None and hasattr(raw_headers, "items"):
        return list(raw_headers.items())
    return list(getattr(response, "headers", {}).items())
