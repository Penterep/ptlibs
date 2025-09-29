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
import re
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
        custom_request_line: Optional[str] = None,
    ) -> 'RawHttpResponse':
        """
        Send a raw HTTP/HTTPS request with full control using http.client.
        Supports optional proxy tunneling for HTTPS using CONNECT.

        If `custom_request_line` is provided, bypasses http.client's request builder
        and sends the request line exactly as given. This allows testing of malformed
        or non-standard HTTP requests.

        Args:
            url (str): Full target URL.
            method (str): HTTP method (GET, POST, PUT, DELETE, etc).
            headers (Optional[Dict[str, str]]): Optional HTTP headers.
            data (Optional[Any]): Optional body as str or bytes.
            timeout (float): Timeout in seconds.
            proxies (Optional[Dict[str, str]]): Dictionary of proxies in requests-compatible format.
            custom_request_line (Optional[str]): If set, sends this exact request line
                instead of constructing one. Example:
                    - "GET / FOO/1.1"
                    - "GET / HTTP/9.8"
                    - "FOO / HTTP/9.8"

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

            if custom_request_line:
                # Send custom / malformed request line manually
                if not getattr(http_conn, "sock", None):
                    http_conn.connect() # ensure socket exists

                if not http_conn.sock:
                    raise ConnectionError(f"Failed to establish socket to {host}:{port}")

                http_conn.sock.sendall((custom_request_line + "\r\n").encode("utf-8"))

                # Ensure Host header exists
                headers = headers.copy() if headers else {}
                if not any(k.lower() == "host" for k in headers):
                    headers["Host"] = parsed.netloc

                # Add accept-encoding header if not provided by user
                if not any(k.lower() == "accept-encoding" for k in headers):
                    headers["Accept-Encoding"] = "gzip, deflate, br"

                # Manually send headers
                for key, value in headers.items():
                    line = f"{key}: {value}\r\n"
                    http_conn.sock.sendall(line.encode("utf-8"))

                if body:
                    http_conn.sock.sendall(f"Content-Length: {len(body)}\r\n".encode("utf-8"))

                # End of headers
                http_conn.sock.sendall(b"\r\n")

                # Send body
                if body:
                    http_conn.sock.sendall(body)


                # Manual reading of response as raw bytes (minimal)
                response_data = b""
                while True:
                    chunk = http_conn.sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk

                # Parse response for custom request line
                status, reason, resp_headers, body_bytes, http_version = self._parse_response_with_custom_request_line(response_data)

                # Build RawHttpResponse with parsed values
                response = RawHttpResponse.__new__(RawHttpResponse)
                response.url = url
                response.status = status
                response.reason = reason
                response.headers = resp_headers
                response.method = custom_request_line.split(" ")[0]
                response.http_version = http_version
                response._content = body_bytes
                response._raw_response = None
                response.msg = None
                return response

            else:
                # Normal path using http.client
                http_conn.putrequest(method.upper(), request_path, skip_host=True)

                if not any(k.lower() == "host" for k in (headers or {})):
                    http_conn.putheader("Host", parsed.netloc)

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

                # Set method and http_version for consistency
                response.method = method.upper()

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


    def _parse_response_with_custom_request_line(self, response_data: bytes):
        """
        Parse raw HTTP response bytes for requests sent with a custom/malformed request line.

        This function MUST ONLY be used for responses from `custom_request_line` requests.
        Normal http.client responses should not use this parser.

        Args:
            response_data (bytes): Full raw response read from socket.

        Returns:
            Tuple[int, str, Dict[str, str], bytes, str]: status, reason, headers dict, body bytes, HTTP version.
        """
        header_end = response_data.find(b"\r\n\r\n")
        if header_end == -1:
            return 0, "", {}, response_data, ""

        header_bytes = response_data[:header_end]
        body_bytes = response_data[header_end + 4:]
        lines = header_bytes.split(b"\r\n")
        if not lines:
            return 0, "", {}, body_bytes, ""

        # Parse status line
        status_line = lines[0].decode("utf-8", errors="replace").strip()
        http_version = ""
        status = 0
        reason = ""

        parts = status_line.split(" ", 2)
        if parts:
            if parts[0].upper().startswith("HTTP/"):
                http_version = parts[0][5:]  # strip 'HTTP/'
                if len(parts) > 1 and parts[1].isdigit():
                    status = int(parts[1])
                if len(parts) > 2:
                    reason = parts[2]
            else:
                # Non-standard/malformed request line, treat method as first part
                http_version = parts[-1] if len(parts) > 1 else ""
                status = 0
                reason = ""

        # Parse headers
        headers = {}
        for line in lines[1:]:
            decoded_line = line.decode("utf-8", errors="replace")
            if ":" in decoded_line:
                key, value = decoded_line.split(":", 1)
                headers[key.lower()] = value.strip()

        return status, reason, headers, body_bytes, http_version


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
        # Convert http.client version integer to string
        version_map = {9: "0.9", 10: "1.0", 11: "1.1"}
        self.http_version = version_map.get(getattr(response, "version", 11), str(getattr(response, "version", 11)))


        self.headers = {k.lower(): v for k, v in response.getheaders()}
        self.msg = response.msg
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