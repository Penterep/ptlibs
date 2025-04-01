from ptlibs.ptprinthelper import ptprint, get_colored_text
from ptlibs import ptprinthelper
import requests
import time
import re

requests.packages.urllib3.disable_warnings()

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
                raise ValueError("Both 'args' and 'ptjsonlib' must be provided")

            self.args = args
            self.ptjsonlib = ptjsonlib
            self.proxy = self.args.proxy

            self.delay = getattr(self.args, 'delay', 0)
            self._initialized = True  # Flag to indicate that initialization is complete

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

    def send_request(self, url, method="GET", *, headers=None, data=None, allow_redirects=True, **kwargs):
        """Wrapper for requests.request that allows dynamic passing of arguments."""
        try:
            response = requests.request(method=method, url=url, allow_redirects=allow_redirects, headers=headers, data=data, proxies=self.proxy if self.proxy else {}, verify=False if self.proxy else True)

            if method.upper() == "GET":
                self._check_fpd_in_response(response)

            if self.delay > 0:
                time.sleep(self.delay / 1000)  # Convert ms to seconds

            return response

        except Exception as e:
            self.ptjsonlib.end_error(f"Error connecting to server: {e}", self.args.json)

    def _check_fpd_in_response(self, response, *, base_indent=4):
        """
        Checks the given HTTP response for Full Path Disclosure (FPD) errors.

        Args:
            response (requests.Response): The HTTP response to check for FPD errors.

        Prints:
            An error message if FPD is found in the response, otherwise indicates no FPD error.
        """
        error_patterns = [
            r"<b>Warning</b>: .* on line.*",
            r"<b>Fatal error</b>: .* on line.*",
            r"<b>Error</b>: .* on line.*",
            r"<b>Notice</b>: .* on line.*"
        ]
        try:
            for pattern in error_patterns:
                match = re.search(pattern, response.text)
                if match:
                    clean_message = re.sub(r"<.*?>", "", match.group(0))
                    ptprint(f"[{response.status_code}] {response.url}\n{' '*(base_indent*2)}{ get_colored_text(clean_message, "ADDITIONS")}", "VULN", condition=not self.args.json, indent=base_indent, clear_to_eol=True)
                    return
        except Exception as e:
            print(f"Error during FPD check: {e}")