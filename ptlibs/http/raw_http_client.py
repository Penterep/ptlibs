"""
raw_http_client.py

Low-level HTTP client for sending raw HTTP/HTTPS requests with full control over method, headers, body, and proxy usage.

This module provides the `RawHttpClient` class, which bypasses high-level HTTP libraries like `requests` and uses the
standard `http.client` and `socket` modules directly. It allows sending malformed or non-standard HTTP requests,
manual proxy tunneling via CONNECT for HTTPS, and fine-grained control over headers and encoding.

Main Components:
- RawHttpClient: Sends raw HTTP(S) requests, optionally through a proxy.
- RawHttpResponse: Wraps the raw response with convenient access to status, headers, and body.

Useful for:
- Debugging malformed HTTP traffic
- Sending requests that must bypass smart behavior of high-level libraries
- Interacting with proxies or inspecting low-level HTTP behavior

Limitations:
- No redirect handling, cookie management, or retries
- SSL certificate verification is disabled (insecure by default)
"""

import socket
import ssl
import urllib.parse
from http.client import HTTPConnection, HTTPSConnection
from typing import Optional, Dict, Any


class RawHttpClient:
    """
    HTTP client for sending raw HTTP requests with full control over headers, method, body, timeout, and proxy support.

    Uses http.client internally for low-level request sending, bypassing higher-level HTTP libraries like `requests`.
    Supports HTTP and HTTPS requests, including tunneling over proxy for HTTPS via the CONNECT method.
    """

    def __init__(self):
        """
        Initialize RawHttpClient.
        """
        pass

    def _send_raw_request(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        timeout: float = 10.0,
        proxies: Optional[Dict[str, str]] = None,
    ) -> 'RawHttpResponse':
        """
        Send a raw HTTP/HTTPS request with full control using http.client.
        Supports optional proxy tunneling for HTTPS using CONNECT.

        Args:
            url (str): Full target URL.
            method (str): HTTP method (GET, POST, PUT, DELETE, etc).
            headers (Optional[Dict[str, str]]): Optional HTTP headers.
            data (Optional[Any]): Optional body as str or bytes.
            timeout (float): Timeout in seconds.
            proxies (Optional[Dict[str, str]]): Dictionary of proxies in requests-compatible format.

        Returns:
            RawHttpResponse: Parsed HTTP response.

        Raises:
            ValueError: On invalid URL.
            TypeError: On invalid data type.
            socket.timeout, ssl.SSLError, OSError: On network-related errors.
        """
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}")

        is_https = parsed.scheme.lower() == "https"
        port = parsed.port or (443 if is_https else 80)
        host = parsed.hostname
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        proxy_url = (proxies or {}).get(parsed.scheme)

        if proxy_url:
            proxy = urllib.parse.urlparse(proxy_url)
            proxy_host = proxy.hostname
            proxy_port = proxy.port or (443 if proxy.scheme == "https" else 80)

            conn = socket.create_connection((proxy_host, proxy_port), timeout=timeout)

            if is_https:
                connect_line = f"CONNECT {host}:{port} HTTP/1.1\r\n"
                connect_headers = f"Host: {host}:{port}\r\n\r\n"
                conn.sendall(connect_line.encode() + connect_headers.encode())

                #response = conn.recv(4096)
                response = self._read_until_double_crlf(conn)
                if b"200 Connection established" not in response:
                    raise ConnectionError("Proxy tunnel failed")

                context = ssl._create_unverified_context()
                conn = context.wrap_socket(conn, server_hostname=host)

            http_conn = HTTPConnection(host, port, timeout=timeout)
            http_conn.sock = conn
        else:
            conn_cls = HTTPSConnection if is_https else HTTPConnection
            ssl_context = ssl._create_unverified_context() if is_https else None
            conn_args = {"context": ssl_context} if ssl_context else {}
            http_conn = conn_cls(host, port, timeout=timeout, **conn_args)

        body = None
        if data is not None:
            if isinstance(data, str):
                body = data.encode("utf-8")
            elif isinstance(data, bytes):
                body = data
            else:
                raise TypeError("Raw request data must be str or bytes")

        try:
            if proxy_url and not is_https:
                request_path = url
            else:
                request_path = path

            http_conn.putrequest(method.upper(), request_path, skip_host=True)

            # Only add Host header if not provided by the user (via headers)
            if not any(k.lower() == "host" for k in (headers or {})):
                host_header = parsed.netloc
                http_conn.putheader("Host", host_header)

            for key, value in (headers or {}).items():
                if key.lower() != "host":
                    http_conn.putheader(key, value)
                else:
                    http_conn.putheader("Host", value)

            if body:
                http_conn.putheader("Content-Length", str(len(body)))

            http_conn.endheaders()

            if body:
                http_conn.send(body)

            raw_response = http_conn.getresponse()
            response = RawHttpResponse(raw_response, url)
            _ = response.content # Force read body to release socket before returning response
            return response

        except (socket.timeout, ssl.SSLError, OSError) as e:
            raise e

        finally:
            try:
                http_conn.close()
            except Exception:
                pass

    def _read_until_double_crlf(self, sock: socket.socket, timeout: float = 10.0) -> bytes:
        """
        Read from socket until we hit double CRLF (\r\n\r\n), which signals end of HTTP headers.
        """
        sock.settimeout(timeout)
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk
        return buffer

class RawHttpResponse:
    """
    Encapsulates a raw HTTP response from http.client with convenient access to status, headers and content.

    Attributes:
        url (str): The requested URL.
        status (int): HTTP status code.
        reason (str): HTTP reason phrase.
        headers (Dict[str, str]): Case-insensitive dict of response headers.
        msg (http.client.HTTPMessage): Full original HTTP header block.
    """

    def __init__(self, response, url: str):
        """
        Initialize RawHttpResponse by reading status, headers, and lazily loading content.

        Args:
            response (http.client.HTTPResponse): The raw HTTP response.
            url (str): The requested URL.
        """
        self.url = url
        self.status = response.status
        self.reason = response.reason
        self.msg = response.msg
        self.headers = {k.lower(): v for k, v in response.getheaders()}
        self._raw_response = response
        self._content = None

    @property
    def content(self) -> bytes:
        """
        Read and cache the full response content as bytes.

        Returns:
            bytes: The response body.
        """
        if self._content is None:
            self._content = self._raw_response.read()
        return self._content

    @property
    def text(self) -> str:
        """
        Decode response content as UTF-8 text with replacement on decode errors.

        Returns:
            str: The response body as string.
        """
        return self.content.decode("utf-8", errors="replace")

    def get_header(self, name: str) -> Optional[str]:
        """
        Case-insensitive access to a response header value.

        Args:
            name (str): Header name.

        Returns:
            Optional[str]: Header value if present, else None.
        """
        return self.headers.get(name.lower())

    def __repr__(self):
        return f"<RawHttpResponse [{self.status} {self.reason}]>"