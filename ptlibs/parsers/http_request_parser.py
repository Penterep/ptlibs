"""This module contains functions used for parsing http requests."""
import urllib
import json
import os
import re
from typing import Union, List, TextIO

from ptlibs.parsers.json_parser import JsonParser
from ptlibs.parsers.xml_parser import XmlParser

class HttpRequestParser():
    def __init__(self, ptjsonlib: object, use_json: bool, placeholder: str = "*"):
        self.ptjsonlib = ptjsonlib
        self.use_json = use_json
        self.placeholder = placeholder
        self._host = None
        self._url = None
        self._request_data = None

    def parse_http_request_to_nodes(self, http_request: str, request_url: str, output_node_types: list = ["request", "url", "parameter", "cookie", "header"]):
        """
        Parses an HTTP request into specified node types.

        Parameters:
        - request: The HTTP request object to parse.
        - output_node_types: A list of node types to extract from the request.
                            Possible values are "request", "url", "parameter",
                            "cookie", and "header". If not specified, all types
                            are returned.

        Returns:
        A dictionary containing the requested node types and their corresponding
        properties.

        Output Node Types:
        - "request": Returns a node with the HTTP method and content type of the request.
        - "url": Parses and returns the URL path as individual nodes.
        - "parameter": Returns nodes representing the parameters in the request body,
                    with properties for name, type (Get, Post, Multipart, Json, xml,
                    Array, Serialized), and value. The method for parsing depends
                    on the Content-Type header.
        - "cookie": Returns a list of all cookies.
        - "header": Returns a list of all headers.

        Example:
        Given a request with the following URL: "http://example.com/dir1/dir2/login.php",
        the "url" node type would return:
        [
            "/",
            "dir1",
            "dir2",
            "login.php"
        ]

        The "parameter" node type will parse the request body according to its content type:
        - If Content-Type is "application/json", it will parse the body as JSON.
        - If Content-Type is "application/xml", it will parse the body as XML.
        - If Content-Type is "multipart/form-data", it will parse the body as multipart data.
        - Additional parsing logic should be implemented for other content types as needed.

        The function ensures that only valid node types are processed.
        """

        result_nodes: list = []
        request_headers = self.get_request_headers(http_request)

        for output_node_type in output_node_types:
            if output_node_type not in output_node_types:
                continue
            else:

                if output_node_type == "request":
                    node = self.ptjsonlib.create_node_object("request")
                    node["properties"].update({"method": http_request.split(" ")[0], "content-type": next((value for key, value in request_headers if key.lower() == "content-type"), None)})
                    result_nodes.append(node)
                    continue

                if output_node_type == "url":
                    parsed_nodes: list = self.ptjsonlib.parse_url2nodes(url=request_url)
                    result_nodes.extend(parsed_nodes)
                    continue

                if output_node_type == "cookie":
                    cookie_headers = [value for key, value in request_headers if key.lower() == "cookie"]
                    for cookie in cookie_headers:
                        cookie_pairs = cookie.split(";")
                        for pair in cookie_pairs:
                            c_name, c_value = pair.strip().split('=', 1)
                            cookie_node = self.ptjsonlib.create_node_object("request_cookies", properties={"name": c_name, "value": c_value})
                            result_nodes.append(cookie_node)

                if output_node_type == "header":
                    headers_dict = {sublist[0]: sublist[1] for sublist in request_headers}
                    for h_key, h_value in headers_dict.items():
                        header_node = self.ptjsonlib.create_node_object("request_headers", properties={"name": h_key, "value": h_value})
                        result_nodes.append(header_node)
                    continue

                if output_node_type == "parameter":
                    request_data = self.get_request_data(http_request)
                    parsed_url = urllib.parse.urlparse(request_url)

                    if parsed_url.query: # parse GET parameters
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        for key, value in query_params.items():
                            parameter_node = self.ptjsonlib.create_node_object("request_parameter", properties={"name": key, "value": value, "type": "GET"})
                            result_nodes.append(parameter_node)

                    if request_data:
                        # TODO: Determinuj content-type, potom to parsuj dle content-type.
                        content_type = next((value for key, value in request_headers if key.lower() == "content-type"), None)

                        if content_type in ["application/x-www-form-urlencoded"]: # parse POST parameters
                            parsed_post_data = urllib.parse.parse_qs(request_data)
                            for key, value in parsed_post_data.items():
                                node = self.ptjsonlib.create_node_object("request_parameter", properties={"name": key, "value": value, "type": "POST"})
                                result_nodes.append(node)

                        elif content_type in ["application/json", "..."]:
                            result_nodes.extend(self.parse_json_to_nodes(request_data))
                            result_nodes.extend(JsonParser(self.ptjsonlib).parse_json_to_nodes(request_data))

                        elif content_type in ["application/xml", "..."]:
                            result_nodes.extend(XmlParser(self.ptjsonlib).parse_xml_to_nodes(request_data))

        result_nodes = sorted(result_nodes, key=lambda x: x['type'])
        return result_nodes

    def parse_http_request(self, http_request: Union[str, TextIO, List[str]]) -> tuple:
        """Parse the provided HTTP request input.

        Args:
            http_request (Union[str, TextIO, List[str]]): The path to a request file,
                                                        a file handler, or a list
                                                        containing HTTP request data.

        Returns:
            tuple: A tuple containing the URL, HTTP method, headers, request data parsed from the HTTP request input.
        """
        headers, request_data = {}, []

        try:
            http_request_str = self._load_and_validate_http_request(http_request)
            # Get method, path, and HTTP version from the first line
            first_line = http_request.split("\n")[0]
            parts = first_line.split()
            method, path, self.HTTP_VERSION = parts[0], parts[1], parts[2]

            # Get headers and request data
            headers = dict(self.get_request_headers(http_request))
            request_data = self.get_request_data(http_request)
            # Set host from headers
            self._host = headers.get("Host")  # Set host based on the Host header
            # Check if host is set
            if self._host is None:
                raise ValueError("Host header is missing from the request.")

            # Construct URL based on path
            if self._host:
                url = f"https://{self._host}{path}"
            else:
                self.ptjsonlib.end_error("Host header is missing in the request file", self.use_json)

            return url, method, headers, request_data

        except FileNotFoundError:
            self.ptjsonlib.end_error("The specified request file does not exist.", self.use_json)
        except IsADirectoryError:
            self.ptjsonlib.end_error("The specified path is a directory, not a file.", self.use_json)
        except Exception as e:
            self.ptjsonlib.end_error(f"Error parsing request file: {e}", self.use_json)

    def check_placeholder(self, url: str, request_data: list, headers: dict):
        """Check if the placeholder character is present in the URL, request data, or headers.

        Args:
            url (str): The URL to check.
            request_data (list): The request data to check.
            headers (dict): The headers to check.
        """
        # Check if placeholder in URL
        if self.placeholder in url:
            return

        # Check if placeholder in request data
        if self.placeholder in ''.join(request_data):
            return

        # Check if placeholder in headers
        for header_key, header_value in headers.items():
            if self.placeholder in header_key or self.placeholder in header_value:
                return

        self.ptjsonlib.end_error("Placeholder character is required in URL, request data, or headers", self.use_json)

    def mark_placeholder(self, http_request: Union[str, TextIO], parameter: str|int) -> str:
        """
        Inserts the placeholder set in `self.placeholder` into the value of a parameter in the given HTTP request.

        Args:
            http_request (str): The raw HTTP request as a string.
            parameter (str|int): The name or index of the parameter whose value should be replaced
                                with the placeholder. If an integer is provided, it will be treated
                                as the index of the parameter in the request. The function will first
                                search for the parameter in the query string (GET parameters), and if
                                not found, it will search in the POST data (form data).

        Returns:
            str: The modified HTTP request with the placeholder (defined in `self.placeholder`) inserted into
                the value of the specified parameter.

        Example:
            If `self.placeholder` is '*' and parameter='user' in the original HTTP request 'user=john',
            the returned request will contain 'user=*'.
        """
        return self._update_parameter_value(http_request=self._load_and_validate_http_request(http_request), parameter=parameter, new_value=self.placeholder)

    def fill_payload(self, http_request: Union[str, TextIO], parameter: str|int, payload: str) -> str:
        """
        Inserts a <payload> into the value of a parameter in the given HTTP request.

        Args:
            http_request (str): The raw HTTP request as a string.
            parameter (str|int): The name or index of the parameter whose value should be replaced
                                    with the provided payload. If an integer is provided, it will be
                                    treated as the index of the parameter in the request. The function
                                    will first search for the parameter in the query string (GET
                                    parameters), and if not found, it will search in the POST data
                                    (form data).
            payload (str): The string payload to be inserted as the value of the specified parameter.

        Returns:
            str: The modified HTTP request with the payload inserted into the value of the specified
                parameter.

        Example:
            If parameter='user' and the original HTTP request contains 'user=john', and payload='admin',
            the returned request will contain 'user=admin'.
        """
        return self._update_parameter_value(http_request=self._load_and_validate_http_request(http_request), parameter=parameter, new_value=payload)

    def _get_content_type(self, headers):
        return next((value for key, value in headers.items() if key.lower() == "content-type"), None)

    def _update_parameter_value(self, http_request: str, parameter: str | int, new_value: str) -> str:
        """
        Updates the specified parameter in GET and POST data with a new value.
        Handles both parameter name (string) and index (int).

        Args:
            http_request (str): The original HTTP request.
            parameter (str | int): The name or index of the parameter to replace.
            new_value (str): The new value to insert for the parameter.

        Returns:
            str: The updated HTTP request string.

        Raises:
            ValueError: If the parameter is not found by name or index in both GET and POST data.
        """
        request_url, request_method, request_headers, request_data = self.parse_http_request(http_request=http_request)
        content_type = next((value for key, value in request_headers.items() if key.lower() == "content-type"), None)

        if isinstance(parameter, str) and parameter.isdigit():
            parameter = int(parameter)
        # Parse URL and parameters
        parsed_url = urllib.parse.urlparse(request_url)
        get_parameters_list: list = urllib.parse.parse_qsl(parsed_url.query)
        post_parameters_dict: dict = self._parse_post_data(request_data, content_type)
        # Update parameters
        if isinstance(parameter, int):
            if parameter < len(get_parameters_list):
                key, _ = get_parameters_list[parameter]
                get_parameters_list[parameter] = (key, new_value)
            elif parameter < len(post_parameters_dict) + len(get_parameters_list):
                key = list(post_parameters_dict.keys())[parameter - len(get_parameters_list)]
                post_parameters_dict[key] = new_value
            else:
                raise IndexError("Parameter index '{parameter}' out of bounds.")
                #self.ptjsonlib.end_error(f"Parameter index '{parameter}' out of bounds.", self.use_json)
        else:
            if parameter in dict(get_parameters_list):
                get_parameters_dict = dict(get_parameters_list)
                get_parameters_dict[parameter] = new_value
                get_parameters_list[:] = list(get_parameters_dict.items())
            elif parameter in post_parameters_dict:
                post_parameters_dict[parameter] = new_value
            else:
                self.ptjsonlib.end_error(
                    f"Parameter '{parameter}' not found in GET or POST data.\n"
                    f"           Available GET parameters: [{', '.join(dict(get_parameters_list).keys())}]\n"
                    f"           Available POST parameters: [{', '.join(post_parameters_dict.keys())}]",
                    self.use_json
                )

        # Reconstruct URL with updated GET parameters
        updated_query = urllib.parse.urlencode(get_parameters_list, safe=self.placeholder)
        updated_url = urllib.parse.urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, updated_query, parsed_url.fragment))

        # Update request_data with modified POST data
        request_data = self._reconstruct_post_data(post_parameters_dict, content_type)

        query_string = f"?{updated_query}" if updated_query else ""


        # Construct the updated HTTP request
        updated_http_request = f"{request_method} {parsed_url.path}{query_string} {self.HTTP_VERSION}" + "\n" + "\n".join(f"{key}: {value}" for key, value in request_headers.items()) + "\n\n" + request_data
        return updated_http_request

    def _parse_post_data(self, request_data: str, content_type: str) -> dict:
        """
        Parses POST data based on the content type.

        Args:
            request_data (str): The raw request data to parse.
            content_type (str): The content type of the request data.

        Returns:
            dict: A dictionary of parsed POST parameters.
        """
        if content_type in ["application/x-www-form-urlencoded", "", None]:
            parsed_qs = urllib.parse.parse_qs(request_data)
            all_keys = set(key.split('=')[0] for key in request_data.split('&') if key)
            # Add missing keys to parsed_qs with empty string value
            for key in all_keys:
                if key not in parsed_qs:
                    parsed_qs[key] = ['']

            # Convert to regular dictionary, extracting the first value if the list contains one item
            parsed_qs_dict = {key: values[0] if values else '' for key, values in parsed_qs.items()}
            return parsed_qs_dict

        elif content_type == "application/json":
            try:
                return json.loads(request_data)
            except json.JSONDecodeError:
                self.ptjsonlib.end_error("Invalid JSON format in request data.", self.use_json)
        elif content_type == "application/xml":
            try:
                root = ET.fromstring(request_data)
                return {elem.tag: elem.text for elem in root}
            except ET.ParseError:
                self.ptjsonlib.end_error("Invalid XML format in request data.", self.use_json)
        return {}

    def _reconstruct_post_data(self, post_parameters_dict: dict, content_type: str) -> str:
        """
        Reconstructs the POST data based on the content type.

        Args:
            post_parameters_dict (dict): The dictionary of POST parameters.
            content_type (str): The content type of the request.

        Returns:
            str: The reconstructed POST data.
        """
        if content_type in ["application/x-www-form-urlencoded", "", None]:
            return urllib.parse.urlencode(post_parameters_dict, safe=self.placeholder)
        elif content_type == "application/json":
            return json.dumps(post_parameters_dict)
        elif content_type == "application/xml":
            root = ET.Element("root")
            for key, value in post_parameters_dict.items():
                elem = ET.SubElement(root, key)
                elem.text = value
            return ET.tostring(root, encoding="unicode")
        else:
            return post_parameters_dict

    def is_valid_http_request(self, request):
        return self._load_and_validate_http_request(request)


    def _load_and_validate_http_request(self, http_request: Union[str, TextIO]) -> str:
        """Load the HTTP request from a file or return the provided request string.

        Args:
            http_request (Union[str, TextIO]): A full HTTP request string
                                                or a path to a request file.

        Returns:
            str: The loaded HTTP request string.

        Raises:
            TypeError: If the input is not a string or file handler.
            FileNotFoundError: If the specified file does not exist.
            IsADirectoryError: If the specified path is a directory.
        """
        if isinstance(http_request, str):
            # Check if it's a path to a file
            if os.path.isfile(http_request):
                with open(http_request, "r") as file:
                    request = file.read()  # Read the file contents
            else:
                request = http_request  # Leave the string as is
        elif hasattr(http_request, 'read'):
            request = http_request.read()  # Read from the file handler
        else:
            raise TypeError("http_request must be a string or a file handler.")

        #print("BEFORE:", request)
        self._validate_http_request(request)
        return request

    def _validate_http_request(self, request) -> bool:
        """
        Validates the structure and content of an HTTP request string.

        Args:
            request (str): The full HTTP request as a string, including request line, headers, and optional body.

        Returns:
            bool: Returns True if the request structure and content are valid.
                Otherwise, uses self.ptjsonlib.end_error to output specific validation errors.
        """

        # Split request into lines
        lines = request.strip().splitlines()

        # Validate the Request Line (allows any method)
        first_line = lines[0].strip()
        if not re.match(r"^[A-Za-z]+\s+\S+\s+HTTP/[\d\.]+$", first_line):
            self.ptjsonlib.end_error("Invalid request line format. Expected format: '<METHOD> <PATH> HTTP/<VERSION>'", self.use_json)

        # Extract Headers
        headers_section = request.split("\n\n")[0].splitlines()[1:]  # Skip the request line
        headers = {line.split(":")[0].strip(): line.split(":")[1].strip() for line in headers_section if ":" in line}

        # Check required Host header
        if "Host" not in headers:
            self.ptjsonlib.end_error("Missing required header: Host", self.use_json)

        # If all checks pass, request is valid
        return True

    def get_request_headers(self, http_request: str):
        request_headers, _, _ = http_request.partition("\n\n")
        request_headers = [line.split(": ", 1) for line in request_headers.split("\n")[1:] if ": " in line]
        return request_headers

    def get_request_data(self, http_request: str):
        _, _, request_data = http_request.partition("\n\n")
        return request_data

    def has_query_params(self, http_request: str):
        http_request = self._load_and_validate_http_request(http_request)
        url, method, headers, request_data = self.parse_http_request(http_request)
        parsed_query: dict = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return bool(parsed_query)

    def build_request(self, url: str, headers: dict, request_data: str = None, method: str = None, http_version: str = "HTTP/1.1"):
        """Builds valid request from provided args"""

        parsed_url = urllib.parse.urlparse(url)
        if not method:
            method = "GET" if not request_data else "POST"
        if not headers.get("Host"):
            headers.update({"Host": parsed_url.netloc})

        query_string = f"?{parsed_url.query}" if parsed_url.query else ""

        result_request = ""
        result_request += f"{method.upper()} {parsed_url.path}{query_string} {http_version.upper()}\n"
        result_request += '\n'.join(f"{key}: {value}" for key, value in headers.items())
        result_request += "\n\n"
        result_request += request_data if request_data else ""
        return result_request

    def get_parameter_name_by_index(self, http_request, parameter_index: int):
        assert type(parameter_index) == int
        url, request_method, headers, request_data = self.parse_http_request(http_request)
        # Parse URL and parameters
        content_type = self._get_content_type(headers)
        parsed_url = urllib.parse.urlparse(url)
        get_parameters_list: list = urllib.parse.parse_qsl(parsed_url.query)
        post_parameters_dict: dict = self._parse_post_data(request_data, content_type)


        if parameter_index < len(get_parameters_list):
            key, _ = get_parameters_list[parameter_index]
            return key
        elif parameter_index < len(post_parameters_dict) + len(get_parameters_list):
            key = list(post_parameters_dict.keys())[parameter_index - len(get_parameters_list)]
            return key
        else:
            raise IndexError("Parameter index '{parameter_index}' out of bounds.")

    