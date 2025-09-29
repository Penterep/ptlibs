import os
import re
import time
import urllib

from threading import Lock

from ptlibs.http.raw_http_client import RawHttpClient
from ptlibs.ptprinthelper import ptprint, get_colored_text
from ptlibs import ptprinthelper

from ptlibs.ptmisclib import load_url_from_web_or_temp

import requests; requests.packages.urllib3.disable_warnings()

class HttpClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Ensures that only one instance of the class is created"""
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, args=None, ptjsonlib=None):
        if not hasattr(self, '_initialized'): # This ensures __init__ is only called once
            if args is None or ptjsonlib is None:
                raise ValueError("PtHttpClient: Error: Both 'args' and 'ptjsonlib' must be provided for init")
            self.args = args
            self.ptjsonlib = ptjsonlib

            def normalize_proxy(raw_proxy):
                if isinstance(raw_proxy, str):
                    return {"http": raw_proxy, "https": raw_proxy}
                elif isinstance(raw_proxy, dict):
                    return raw_proxy
                return None

            self.proxy = normalize_proxy(args.proxy) if hasattr(args, 'proxy') else None
            self.timeout = getattr(self.args, 'timeout', 10)
            self._store_urls: bool = False
            self._stored_urls = set()
            self._base_headers: dict = None
            self._initialized = True  # Flag to indicate that initialization is complete
            self._lock = Lock()
            self._raw_http_client: object = RawHttpClient()

    @classmethod
    def get_instance(cls, args=None, ptjsonlib=None):
        """
        Returns the singleton instance of the HttpClient.

        If the instance does not exist yet, it will be created using the provided
        `args` and `ptjsonlib`. Subsequent calls will return the already created instance.

        Args:
            args (optional): Initialization arguments required on first instantiation.
            ptjsonlib (optional): Additional initialization object required on first instantiation.

        Raises:
            ValueError: If called for the first time without required `args` or `ptjsonlib`.

        Returns:
            HttpClient: The singleton HttpClient instance.
        """
        if cls._instance is None:
            if args is None or ptjsonlib is None:
                raise ValueError("HttpClient must be initialized with args and ptjsonlib")
            cls._instance = cls(args, ptjsonlib)
        return cls._instance


    def send_request(self, url, method="GET", *, headers=None, data=None, allow_redirects=True, cookies: dict = {}, timeout=None, verify=False, cache=None, dump=False, store_urls=False, merge_headers=True, **kwargs):
        """
        Send an HTTP request with support for caching.

        Args:
            url (str): Target URL.
            method (str, optional): HTTP method to use (e.g., "GET", "POST"). Defaults to "GET".
            headers (dict, optional): Request-specific headers. If ``merge_headers=True``,
                they will be merged with the default/base headers.
            data (Any, optional): Request body or payload (e.g., dict for form data, str/bytes, or JSON).
            allow_redirects (bool, optional): Whether to follow redirects. Defaults to True.
            cookies (dict, optional): Cookies to attach to the request. Defaults to {}.
            timeout (float or tuple, optional): Timeout in seconds for the request (same as in ``requests``).
            verify (bool or str, optional): Whether to verify SSL certificates. Defaults to False.
            cache (bool, optional): If True, responses may be cached and served from cache on repeat requests.
            dump (bool, optional): If True, dumps the raw request/response for debugging.
            store_urls (bool, optional): If True, internally stores successfully requested URLs (non-404).
            merge_headers (bool, optional): If True, merges default headers with provided ``headers``.
            **kwargs: Additional keyword arguments passed directly to ``requests.request()``.

        Returns:
            requests.Response: Response object from the executed HTTP request.
        """
        try:
            if cache is None and hasattr(kwargs.get('args', None), 'cache'):
                cache = kwargs['args'].cache
            final_headers = self._merge_headers(headers, merge_headers)
            timeout = timeout or self.timeout

            response = load_url_from_web_or_temp(
                url=url,
                method=method,
                headers=final_headers,
                proxies=self.proxy if self.proxy else {},
                data=data,
                timeout=timeout,
                redirects=allow_redirects,
                verify=verify,
                dump_response=dump,
                cache=cache
                )

            """
            response = requests.request(method=method, url=url, allow_redirects=allow_redirects, headers=final_headers, data=data, timeout=timeout, proxies=(self.proxy if self.proxy else {}), verify=(False if self.proxy else True))
            """

            if method.upper() == "GET":
                with self._lock:
                    self._check_fpd_in_response(response)

            if self._store_urls or store_urls:
                if response.status_code != 404:
                    with self._lock:
                        self._stored_urls.add(response.url)

            if hasattr(self.args, 'delay') and self.args.delay > 0:
                time.sleep(self.args.delay / 1000)  # Convert ms to seconds

            return response

        except Exception as e:
            self._remap_requests_exception(e)

    def send_raw_request(self, url, method="GET", *, headers=None, data=None, timeout=None, proxies=None, custom_request_line=None):
        """
        Send a raw HTTP request using the internal RawHttpClient with full control.

        This method provides low-level request capabilities, including:
            - Sending malformed or non-standard HTTP requests.
            - Bypassing high-level HTTP libraries like `requests`.
            - Optional proxy tunneling for HTTPS.
            - Full control over headers, method, body, and timeout.
        The request is sent in a thread-safe manner using an internal lock.

        Args:
            url (str): Target URL for the request.
            method (str): HTTP method to use (default: "GET"). Ignored if `custom_request_line` is set.
            headers (dict, optional): Custom HTTP headers to send.
            data (str or bytes, optional): Raw request body.
            timeout (float, optional): Timeout in seconds. Defaults to client's configured timeout.
            proxies (dict, optional): Proxy dictionary in requests-compatible format.
            custom_request_line (str, optional): If set, sends this exact request line instead of constructing one.
                Examples:
                    - "GET / FOO/1.1"
                    - "GET / HTTP/9.8"
                    - "FOO / HTTP/9.8"

        Returns:
            RawHttpResponse: Response object with `.status`, `.headers`, `.text`, `.content`, etc.

        Raises:
            Exception: Propagates any error raised by the raw HTTP client.
        """
        try:
            with self._lock:
                response = self._raw_http_client._send_raw_request(
                    url=url,
                    method=method,
                    headers=headers,
                    data=data,
                    timeout=timeout,
                    proxies=self.proxy,
                    custom_request_line=custom_request_line
                )
                return response
        except Exception as e:
            raise e

    def _merge_headers(self, headers: dict | None, merge: bool) -> dict:
        """
        Merge base headers with user-provided headers based on the merge flag.

        Args:
            headers (dict | None): Headers provided during the request.
            merge (bool): If True, combine base headers with user headers.

        Returns:
        """
        if merge:
            return {**(self._base_headers or {}), **(headers or {})}
        return headers or {}

    def is_valid_url(self, url):
        # A basic regex to validate the URL format
        regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'  # ...or ipv4
            r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # ...or ipv6
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return re.match(regex, url) is not None

    def _extract_unique_directories(self, target_domain: str = None, urls: list = None):
        """
        Extracts unique directories from a list of URLs.
        If target_domain is specified, only URLs matching the domain are processed.
        If urls are provided, they are used instead of self._stored_urls.
        """

        unique_directories = set()
        urls = urls or self._stored_urls  # Use provided URLs or fallback to stored ones
        for url in self._stored_urls:
            parsed_url = urllib.parse.urlparse(url)
            if target_domain is None or parsed_url.netloc == target_domain:  # Filter if target_domain is set
                path_parts = parsed_url.path.strip("/").split("/")

                for i in range(len(path_parts)):
                    directory_path = "/" + "/".join(path_parts[:i + 1])
                    if not os.path.splitext(directory_path)[1]:  # Exclude if it has a file extension
                        if not directory_path.endswith('/'):
                            directory_path += '/'
                        unique_directories.add(directory_path)

        return sorted(list(unique_directories))  # Sort for consistency


    def _check_fpd_in_response(self, response, *, base_indent=4):
        """
        Checks the given HTTP response for Full Path Disclosure (FPD) errors.

        Args:
            response (requests.Response): The HTTP response to check for FPD errors.

        Prints:
            An error message or extracted path if found in the response.
        """

        error_patterns = [
            r"<b>Warning</b>: .* on line.*",
            r"<b>Fatal error</b>: .* on line.*",
            r"<b>Error</b>: .* on line.*",
            r"<b>Notice</b>: .* on line.*",
            #r"(<b>)?Uncaught Exception(</b>)?: [.\s]* on line.*",
            #r"(?:in\s+)([a-zA-Z]:\\[\\\w.-]+|\/[\w.\/-]+)",  # Windows or Unix full file paths
        ]
        path_extractor = r"(in\s+(?:[a-zA-Z]:\\[^\s]+|/[\w./\-_]+))"

        try:
            response._is_fpd_vuln = any_vuln = False
            printed_paths = set()  # Track already printed paths/messages

            for pattern in error_patterns:
                matches = re.finditer(pattern, response.text)
                for match in matches:
                    if not any_vuln:
                        ptprint(f"[{response.status_code}] {response.url}", "VULN", condition=not self.args.json, indent=base_indent, clear_to_eol=True)
                        response._is_fpd_vuln = any_vuln = True

                    raw_message = match.group(0)
                    text_only = re.sub(r'<[^>]+>', '', raw_message)
                    if text_only not in printed_paths:
                        ptprint(f"{get_colored_text(text_only, 'ADDITIONS')}", "TEXT", condition=not self.args.json, indent=base_indent * 2, clear_to_eol=True)
                        printed_paths.add(text_only)

                    """
                    clean_message = re.sub(r"<.*?>", "", raw_message)

                    # Try to extract just the "in ..." path
                    path_match = re.search(path_extractor, clean_message)
                    if path_match:
                        display = path_match.group(1)
                    else:
                        display = clean_message

                    # Check if the path/message has already been printed
                    if display not in printed_paths:
                        ptprint(f"{get_colored_text(display, 'ADDITIONS')}", "TEXT", condition=not self.args.json, indent=base_indent * 2, clear_to_eol=True)
                        printed_paths.add(display)
                    """
        except Exception as e:
            pass


    def _remap_requests_exception(self, exc):
        """
        Remap exceptions from `requests` library to the same exception types
        but with shorter, clearer messages.

        Args:
            exc (Exception): The original exception raised by the `requests` library.

        Raises:
            requests.exceptions.RequestException: remapped exception with clearer message.
            Exception: re-raises the original exception if it's not recognized.
        """
        def remap_exception(exc_type, message):
            new_exc = exc_type(message)
            raise new_exc from exc

        if isinstance(exc, requests.exceptions.ConnectionError):
            msg = str(exc).lower()
            if "name or service not known" in msg or "nodename nor servname provided" in msg:
                remap_exception(requests.exceptions.ConnectionError, "DNS error: domain name not found")
            elif "connection refused" in msg:
                remap_exception(requests.exceptions.ConnectionError, "Connection refused by the server")
            elif "sslerror" in msg:
                remap_exception(requests.exceptions.ConnectionError, "SSL error occured")
            else:
                remap_exception(requests.exceptions.ConnectionError, "Connection error occurred")

        elif isinstance(exc, requests.exceptions.Timeout):
            remap_exception(requests.exceptions.Timeout, "Request timed out")

        elif isinstance(exc, requests.exceptions.HTTPError):
            status = getattr(exc.response, "status_code", "unknown")
            remap_exception(requests.exceptions.HTTPError, f"HTTP error occurred: status code {status}")

        elif isinstance(exc, requests.exceptions.InvalidURL):
            remap_exception(requests.exceptions.InvalidURL, "Invalid URL provided")

        elif isinstance(exc, requests.exceptions.URLRequired):
            remap_exception(requests.exceptions.URLRequired, "A valid URL is required")

        elif isinstance(exc, requests.exceptions.TooManyRedirects):
            remap_exception(requests.exceptions.TooManyRedirects, "Too many redirects")

        elif isinstance(exc, requests.exceptions.InvalidSchema):
            remap_exception(requests.exceptions.InvalidSchema, "Invalid URL schema")

        elif isinstance(exc, requests.exceptions.ChunkedEncodingError):
            remap_exception(requests.exceptions.ChunkedEncodingError, "Chunked encoding error")

        elif isinstance(exc, requests.exceptions.ContentDecodingError):
            remap_exception(requests.exceptions.ContentDecodingError, "Content decoding failed")

        elif isinstance(exc, requests.exceptions.StreamConsumedError):
            remap_exception(requests.exceptions.StreamConsumedError, "Response stream already consumed")

        elif isinstance(exc, requests.exceptions.RetryError):
            remap_exception(requests.exceptions.RetryError, "Max retries exceeded")

        elif isinstance(exc, requests.exceptions.SSLError):
            remap_exception(requests.exceptions.SSLError, "SSL error occured")

        elif isinstance(exc, requests.exceptions.RequestException):
            remap_exception(requests.exceptions.RequestException, "General HTTP request error")

        else:
            raise exc
