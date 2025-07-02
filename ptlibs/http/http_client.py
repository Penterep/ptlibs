import os
import re
import time
import urllib

from threading import Lock
from ptlibs.ptprinthelper import ptprint, get_colored_text
from ptlibs import ptprinthelper

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
            self.proxy = self.args.proxy
            self.timeout = self.args.timeout
            self._store_urls: bool = False
            self._stored_urls: bool = set()
            self._base_headers: dict = None
            self._initialized = True  # Flag to indicate that initialization is complete
            self._lock = Lock()

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

    def send_request(self, url, method="GET", *, headers=None, data=None, allow_redirects=True, store_urls=False, merge_headers=True, timeout=None, **kwargs):
        """
        Send an HTTP request with optional base header merging and custom options.

        Args:
            url (str): Target URL.
            method (str): HTTP method (GET, POST, etc.).
            headers (dict, optional): Request-specific headers.
            data (Any, optional): Payload to send (form data, JSON, etc.).
            allow_redirects (bool): Whether to follow redirects.
            store_urls (bool): Whether to store non-404 URLs internally.
            merge_headers (bool): If True, merges base headers with provided headers.
            **kwargs: Additional parameters passed to `requests.request`.

        Returns:
            requests.Response: The HTTP response object.
        """
        try:
            final_headers = self._merge_headers(headers, merge_headers)
            timeout = timeout or self.timeout
            self.response =  response = requests.request(method=method, url=url, allow_redirects=allow_redirects, headers=final_headers, data=data, timeout=timeout, proxies=(self.proxy if self.proxy else {}), verify=(False if self.proxy else True))

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
            self.response._is_fpd_vuln = any_vuln = False
            printed_paths = set()  # Track already printed paths/messages

            for pattern in error_patterns:
                matches = re.finditer(pattern, response.text)
                for match in matches:
                    if not any_vuln:
                        ptprint(f"[{response.status_code}] {response.url}", "VULN", condition=not self.args.json, indent=base_indent, clear_to_eol=True)
                        self.response._is_fpd_vuln = any_vuln = True


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
            print(f"Error during FPD check: {e}")