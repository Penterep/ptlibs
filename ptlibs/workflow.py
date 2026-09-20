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
    load_workflow(workflow_file) -> list
"""

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

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
                      extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None) -> WorkflowResult:
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
        )
        variables.update(result.variables)
        step_results.append(result)

    return WorkflowResult(variables=variables, steps=step_results)


def execute_step(step: dict, variables: dict, ptjsonlib: object = None, http_client: object = None,
                  use_json: bool = False, method_override: Optional[str] = None,
                  extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None) -> StepResult:
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
                                 method_override=method_override, extra_headers=extra_headers, allow_redirects=allow_redirects)
        raw_text = _raw_response_text(response)
    else:
        raise ValueError(f"Unknown workflow action: {action!r}")

    return StepResult(variables=_extract_variables(step.get("regex"), raw_text), response=response)


def send_request(step: dict, variables: dict, ptjsonlib: object = None, http_client: object = None,
                  use_json: bool = False, method_override: Optional[str] = None,
                  extra_headers: Optional[dict] = None, allow_redirects: Optional[bool] = None):
    """Send the raw HTTP request described by a "send_request" step, with {{name}} placeholders
    in step["content"] filled in from variables, and return the resulting requests.Response.

    method_override, if given, replaces the parsed HTTP method (only the verb changes -
    the body/headers are still sent as templated). extra_headers, if given, is merged over
    the parsed headers (it wins on a name clash). allow_redirects, if not None, is passed
    through to http_client.send_request (otherwise its own default applies).
    """
    schema = step.get("schema", "https")
    content = substitute_variables(step["content"], variables)

    parser = HttpRequestParser(ptjsonlib, use_json=use_json)
    url, method, headers, data = parser.parse_http_request(content, scheme=schema)
    if extra_headers:
        headers = {**headers, **extra_headers}

    kwargs = {} if allow_redirects is None else {"allow_redirects": allow_redirects}
    return http_client.send_request(url=url, method=method_override or method, headers=headers, data=data or None, **kwargs)


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
