import re
from urllib.parse import unquote, urlparse, urlunparse

from ptlibs.ptnethelper import is_valid_ip_address
from ptlibs.ptpathtypedetector import PtPathTypeDetector

class UrlParser():
    INPUT_PLACEHOLDER = "{{*}}"
    HASH_LENGTHS = [32, 40, 56, 64, 96, 128]

    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

    def parse_url_to_nodes(self, url: str, method: str, status_code: str, data: str = None, headers: str = "", known_nodes: list = None, respect_param_values: bool = False) -> list[dict]:
        """
        Parses the given request into webSource, action and webInput nodes and returns them as a list.

        Args:
            url (str): The requested URL, including its query parameters.
            method (str): The HTTP method of the request.
            status_code (str): The HTTP status code of the response.
            data (str, optional): The POST data of the request. Defaults to None.
            headers (str, optional): The HTTP headers of the request, separated by \\r\\n. Defaults to "".
            known_nodes (list, optional): A list of known nodes. If provided, the function returns only nodes
                that are not included in this list. Defaults to None.
            respect_param_values (bool, optional): If True, requests that differ only in parameter values are
                separate actions. If False, they are considered duplicates. Defaults to False.

        Returns:
            list[dict]: A list of node dictionaries representing the request.

        Note:
            Every part of the URL becomes a webSource node, but only the requested one gets an action node,
            as nothing is known about the response of the others. Every parameter of the action becomes a webInput node.
        """

        new_nodes = []
        known_nodes = known_nodes or []
        source_key = self._add_source_nodes(url, new_nodes, known_nodes)

        parsed_url = urlparse(url)
        query_params = self._split_params(parsed_url.query)
        data_params = self._split_params(data)

        action_name = " ".join(filter(None, [method, "&".join(query_params + data_params)]))
        if self._is_known_action(source_key, action_name, known_nodes, respect_param_values):
            return new_nodes

        def create_request(query: str, body: str) -> str:
            path = urlunparse(("", "", parsed_url.path or "/", "", query, ""))
            return self.create_request_content(method, path, parsed_url.netloc, headers, body)

        action_properties = {"name": action_name, "httpMethod": method, "httpStatusCode": status_code, "httpRequest": create_request(parsed_url.query, data)}
        action_node = self.ptjsonlib.create_node_object("action", None, source_key, action_properties)
        new_nodes.append(action_node)

        for index, param in enumerate(query_params):
            http_request = create_request(self._mark_param(query_params, index), data)
            new_nodes.append(self._create_input_node(param, http_request, action_node["key"]))
        for index, param in enumerate(data_params):
            http_request = create_request(parsed_url.query, self._mark_param(data_params, index))
            new_nodes.append(self._create_input_node(param, http_request, action_node["key"]))
        return new_nodes


    def parse_url_list_to_nodes(self, urls: list[dict], headers: str = "", known_nodes: list = None, respect_param_values: bool = False) -> list[dict]:
        """
        Parses a list of requests into their separate components and returns them as a list of nodes.

        Args:
            urls (list[dict]): A list of requests, each with the keys "url", "method", "statusCode" and optionally "data".
            headers (str, optional): The HTTP headers shared by all the requests, separated by \\r\\n. Defaults to "".
            known_nodes (list, optional): A list of known nodes. If provided, the function filters out nodes
                that already exist in this list. Defaults to None.
            respect_param_values (bool, optional): If True, requests that differ only in parameter values are
                separate actions. If False, they are considered duplicates. Defaults to False.

        Returns:
            list[dict]: A list of node dictionaries representing the requests.

        Note:
            This function iterates through the list of requests and parses each of them using the parse_url_to_nodes
            method. It then extends the list of known_nodes with the parsed nodes. If known_nodes is not provided, a new list is used.
        """

        known_nodes = known_nodes or []
        assert isinstance(known_nodes, list)
        for item in urls:
            known_nodes.extend(self.parse_url_to_nodes(item["url"], item["method"], item["statusCode"], item.get("data"), headers, known_nodes, respect_param_values))
        return known_nodes


    def create_request_content(self, method: str, path: str, domain: str, headers: str = "", data: str = None) -> str:
        """
        Creates the text of an HTTP request.

        Args:
            method (str): The HTTP method of the request.
            path (str): The path of the request, including its query parameters.
            domain (str): The value of the Host header.
            headers (str, optional): The HTTP headers of the request, separated by \\r\\n. Defaults to "".
            data (str, optional): The POST data of the request. Defaults to None.

        Returns:
            str: The text of the HTTP request.
        """

        request_content = f"{method} {path} HTTP/1.1\r\n"
        request_content += f"Host: {domain}\r\n"
        if headers:
            request_content += f"{headers}\r\n"
        if data:
            if "content-type:" not in headers.lower():
                request_content += "Content-Type: application/x-www-form-urlencoded\r\n"
            request_content += f"Content-Length: {len(data.encode())}\r\n"
        request_content += "Connection: close\r\n\r\n"
        if data:
            request_content += data
        return request_content


    def get_input_type(self, value: str) -> str:
        """
        Determines the data type of the given parameter value.

        Args:
            value (str): The URL decoded parameter value.

        Returns:
            str: One of hash, ip, phone, integer, float, url, email, filename or string.

        Note:
            The order of the checks matters, e.g. +420777123456 would also pass as an integer.
        """

        if len(value) in self.HASH_LENGTHS and re.fullmatch(r"[0-9a-fA-F]+", value):
            return "hash"
        if is_valid_ip_address(value):
            return "ip"
        if self._is_phone(value):
            return "phone"
        if re.fullmatch(r"[+-]?[0-9]+", value):
            return "integer"
        if re.fullmatch(r"[+-]?[0-9]*[.,][0-9]+", value):
            return "float"
        if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.\-]*://\S+|//\S+|www\.\S+", value):
            return "url"
        if re.fullmatch(r"[^@\s:/]+@[^@\s:/]+\.[^@\s:/.]+", value):
            return "email"
        if self._is_filename(value):
            return "filename"
        return "string"


    def get_base_url(self, url: str) -> str:
        """Returns base url"""
        parsed_url = urlparse(url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}"

    def get_paths(self, url: str) -> list[str]:
        """Returns paths from url"""
        return [segment for segment in urlparse(url).path.split("/") if segment]

    def _add_source_nodes(self, url: str, new_nodes: list, known_nodes: list) -> str:
        """Adds missing webSource nodes of the url to new_nodes and returns the key of the last one"""
        base_url = self.get_base_url(url)
        root_properties = {"name": "/", "url": base_url, "webSourceType": "webSourceTypeDirectory"}
        parent = self._add_source_node("group_web_sources", None, root_properties, new_nodes, known_nodes)
        paths = self.get_paths(url)
        for index, path in enumerate(paths):
            properties = {"name": path, "url": f"{base_url}/{'/'.join(paths[0:index+1])}", "webSourceType": PtPathTypeDetector().get_type(path)}
            parent = self._add_source_node(None, parent, properties, new_nodes, known_nodes)
        return parent

    def _add_source_node(self, parent_type: str, parent: str, properties: dict, new_nodes: list, known_nodes: list) -> str:
        """Adds webSource node to new_nodes if it is not known yet and returns its key"""
        node_object = self.ptjsonlib.create_node_object("webSource", parent_type, parent, properties, new_nodes, known_nodes)
        if type(node_object) is not str:
            new_nodes.append(node_object)
            return node_object["key"]
        return node_object

    def _create_input_node(self, param: str, http_request: str, parent: str) -> dict:
        """Creates webInput node from the given name=value parameter"""
        name, _, value = param.partition("=")
        properties = {"name": unquote(name), "inputType": self.get_input_type(unquote(value)), "httpRequest": http_request}
        return self.ptjsonlib.create_node_object("webInput", None, parent, properties)

    def _is_known_action(self, source_key: str, action_name: str, known_nodes: list, respect_param_values: bool) -> bool:
        """Returns True if the source already has this action. Checked here because node_duplicity_check ignores the parent."""
        action_id = self._get_action_id(action_name, respect_param_values)
        for node in known_nodes:
            if node["type"] == "action" and node["parent"] == source_key:
                if self._get_action_id(node["properties"]["name"], respect_param_values) == action_id:
                    return True
        return False

    def _get_action_id(self, action_name: str, respect_param_values: bool) -> tuple:
        """Returns what identifies an action: its method and parameters in any order, with values only if respected"""
        method, _, params = action_name.partition(" ")
        params = self._split_params(params)
        if not respect_param_values:
            params = [param.partition("=")[0] for param in params]
        return method, sorted(params)

    def _split_params(self, params: str) -> list[str]:
        """Returns the name=value parts of the given query or POST data"""
        return [param for param in (params or "").split("&") if param]

    def _mark_param(self, params: list[str], index: int) -> str:
        """Returns the parameters joined back together with the value at the given index replaced by the placeholder"""
        marked_params = params.copy()
        marked_params[index] = f"{params[index].partition('=')[0]}={self.INPUT_PLACEHOLDER}"
        return "&".join(marked_params)

    def _is_phone(self, value: str) -> bool:
        """Returns True for 9-15 digits with an international prefix (+, 00) or with separators"""
        if re.fullmatch(r"(?:\+|00)[1-9](?:[ +.\-()/]?[0-9]){8,14}", value):
            return True
        return bool(re.fullmatch(r"(?=(?:[^0-9]*[0-9]){9,15}[^0-9]*$)\(?[0-9]{2,4}\)?(?:[ +\-][0-9]{2,4}){2,4}", value))

    def _is_filename(self, value: str) -> bool:
        """Returns True for a file path or a name with an extension known to PtPathTypeDetector"""
        if re.fullmatch(r"(?:\.{0,2}[\\/]|[a-zA-Z]:\\)\S*[^\\/\s]", value):
            return True
        name = re.split(r"[\\/]", value)[-1].lower()
        if name.endswith(".com"):
            return False
        return PtPathTypeDetector().get_type(name) not in ("webSourceTypeDirectory", "webSourceTypeOther")
