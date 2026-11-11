import base64
import binascii
import json
import re
from dataclasses import dataclass
from urllib.parse import quote_plus, unquote, urlparse, urlunparse
from xml.etree import ElementTree

from ptlibs.ptnethelper import is_valid_ip_address
from ptlibs.ptpathtypedetector import PtPathTypeDetector


@dataclass(eq=False)
class _Param:
    """One name=value parameter of a query string or of a request body. Compared by identity."""
    raw: str
    raw_name: str
    name: str
    value: str
    form_type: str = None
    required: bool = False
    default_type: str = "String"


class UrlParser():
    INPUT_PLACEHOLDER = "{{*}}"
    HASH_LENGTHS = [32, 40, 64, 128]
    FLOAT_PATTERN = r"[+-]?[0-9]*[.,][0-9]+"
    FORM_URLENCODED = "application/x-www-form-urlencoded"
    MULTIPART_FORM_DATA = "multipart/form-data"
    MULTIPART_BOUNDARY = "----PenterepFormBoundary7MA4YWxkTrZu0gW"
    GENERATED_HEADERS = {"host", "content-length", "connection"}
    BOOLEAN_VALUES = {"on", "off", "true", "false", "enable", "disable"}
    PHP_SERIALIZED_PATTERN = r'N;|b:[01];|i:-?\d+;|d:-?(?:\d+(?:\.\d+)?(?:E[+-]?\d+)?|INF|NAN);|s:\d+:".*";|a:\d+:\{.*\}|[OC]:\d+:"[^"]+":\d+:\{.*\}'
    SERIALIZED_SIGNATURES = (b"\xac\xed\x00\x05", b"\x00\x01\x00\x00\x00\xff\xff\xff\xff", b"\xff\x01", b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05")

    FORM_INPUT_TYPES = {
        "password": "Password",
        "email": "Email",
        "phone": "Phone", "tel": "Phone",
        "number": "Integer", "range": "Integer",
        "date": "Date", "month": "Date", "week": "Date",
        "datetime": "Datetime", "datetime-local": "Datetime",
        "time": "Time",
        "boolean": "Boolean", "checkbox": "Boolean", "radio": "Boolean",
        "file": "Filename",
        "url": "Url",
    }

    NAME_INPUT_TYPES = [
        (["captcha"], "Captcha"),
        (["email", "mail", "e-mail"], "Email"),
        (["phone", "mobile", "telefon"], "Phone"),
        (["guid"], "Guid"),
        (["id", "count", "number"], "Integer"),
        (["file", "upload", "attachment", "filename"], "Filename"),
        (["secret", "token", "key", "api"], "Token"),
        (["csrf", "csrftoken", "csrf-token", "csrf_token"], "CsrfToken"),
        (["login", "username"], "Username"),
        (["ipaddress", "ip-address", "ip_address"], "Username"),
        (["sid", "sessionid", "JSESSIONID", "ASP.NET_SessionId"], "SessionId"),
        (["password", "pass"], "Password"),
        (["is_", "has_", "bool", "enabled", "checked", "remember"], "Boolean"),
        (["id_", "_id", "ID", "Id"], "Boolean"),
        (["str", "string", "query"], "String"),
        (["hash"], "Hash"),
        (["ticket"], "Token"),
        (["referer", "referrer", "url", "path", "backurl", "returnurl"], "Path"),
    ]

    RESPONSE_TYPES = {
        "text/html": "Html", "application/xhtml+xml": "Html",
        "application/json": "Json", "text/json": "Json",
        "application/xml": "Xml", "text/xml": "Xml",
        "application/rss+xml": "Rss", "application/atom+xml": "Rss",
        "text/plain": "Text",
        "text/css": "Css",
        "application/javascript": "JavaScript", "text/javascript": "JavaScript", "application/x-javascript": "JavaScript",
        "application/ecmascript": "JavaScript", "text/ecmascript": "JavaScript",
        "application/pdf": "Document", "application/msword": "Document", "application/rtf": "Document", "text/csv": "Document",
        "application/zip": "Archive", "application/gzip": "Archive", "application/x-gzip": "Archive", "application/x-tar": "Archive",
        "application/x-7z-compressed": "Archive", "application/x-rar-compressed": "Archive", "application/vnd.rar": "Archive",
        "application/x-bzip2": "Archive",
        "application/octet-stream": "Binary",
    }
    DOCUMENT_TYPE_PREFIXES = ("application/vnd.openxmlformats-officedocument.", "application/vnd.ms-", "application/vnd.oasis.opendocument.")

    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

    def parse_url_to_nodes(self, url: str, method: str, status_code: str, data: str | bytes = None, headers: dict | str = None, known_nodes: list = None, respect_param_values: bool = False, content_type: str = None) -> list[dict]:
        """
        Parses the given request into webSource, action and webInput nodes and returns them as a list.

        Args:
            url (str): The requested URL, including its query parameters.
            method (str): The HTTP method of the request.
            status_code (str): The HTTP status code of the response.
            data (str | bytes, optional): The POST data of the request. Defaults to None.
            headers (dict | str, optional): The HTTP headers of the request, as a dictionary or separated by \\r\\n. Defaults to None.
            known_nodes (list, optional): A list of known nodes. If provided, the function returns only nodes
                that are not included in this list. Defaults to None.
            respect_param_values (bool, optional): If True, requests that differ only in parameter values are
                separate actions. If False, they are considered duplicates. Defaults to False.
            content_type (str, optional): The Content-Type of the response, returned as webActionResponseType. Defaults to None.

        Returns:
            list[dict]: A list of node dictionaries representing the request.

        Note:
            Every part of the URL becomes a webSource node, but only the requested one gets an action node,
            as nothing is known about the response of the others. Every parameter of the action becomes a webInput node.
            An empty query parameter whose name does not tell its type has no webInputType.
        """

        new_nodes = []
        known_nodes = known_nodes or []
        source_key = self._add_source_nodes(url, new_nodes, known_nodes)

        if isinstance(data, bytes):
            data = data.decode(errors="replace")
        data = data or None
        parsed_url = urlparse(url)
        query_params = self._parse_params(parsed_url.query)
        data_params = self._parse_params(data, "String")

        def create_request(marked_param: _Param = None) -> str:
            query = self._join_params(query_params, marked_param) if marked_param in query_params else parsed_url.query
            body = self._join_params(data_params, marked_param) if marked_param in data_params else data
            return self.create_request_content(method, self._get_request_path(parsed_url, query), parsed_url.netloc, headers, body)

        new_nodes.extend(self._create_action_nodes(source_key, method, status_code, content_type, query_params + data_params, create_request, known_nodes, respect_param_values))
        return new_nodes


    def parse_form_to_nodes(self, form: dict, headers: dict | str = None, known_nodes: list = None, respect_param_values: bool = False) -> list[dict]:
        """
        Parses the given HTML form into webSource, action and webInput nodes and returns them as a list.

        Args:
            form (dict): The form with the keys "action" (or "url"), "method", "enctype" and "parameters",
                each parameter with the keys "name", "type", "value" and "required".
            headers (dict | str, optional): The HTTP headers of the request, as a dictionary or separated by \\r\\n. Defaults to None.
            known_nodes (list, optional): A list of known nodes. If provided, the function returns only nodes
                that are not included in this list. Defaults to None.
            respect_param_values (bool, optional): If True, requests that differ only in parameter values are
                separate actions. If False, they are considered duplicates. Defaults to False.

        Returns:
            list[dict]: A list of node dictionaries representing the form.

        Note:
            The form is not submitted, so its action has no status code and no response type. A GET form sends its
            parameters in the query string, which replaces the query string of the action URL like browsers do.
            Other forms send them in the body encoded according to enctype, which is multipart/form-data or, by default,
            application/x-www-form-urlencoded.
        """

        new_nodes = []
        known_nodes = known_nodes or []
        url = form.get("action") or form.get("url")
        if not url:
            return new_nodes
        source_key = self._add_source_nodes(url, new_nodes, known_nodes)

        method = (form.get("method") or "GET").upper()
        parsed_url = urlparse(url)
        form_params = [self._create_form_param(parameter) for parameter in form.get("parameters") or []]
        if method == "GET":
            query_params, body_params = form_params, None
        else:
            query_params, body_params = self._parse_params(parsed_url.query), form_params
        is_multipart = (form.get("enctype") or "").lower().startswith(self.MULTIPART_FORM_DATA)

        def create_request(marked_param: _Param = None) -> str:
            path = self._get_request_path(parsed_url, self._join_params(query_params, marked_param))
            if body_params is None:
                return self.create_request_content(method, path, parsed_url.netloc, headers)
            if is_multipart:
                body = self._create_multipart_body(body_params, marked_param)
                return self.create_request_content(method, path, parsed_url.netloc, headers, body, f"{self.MULTIPART_FORM_DATA}; boundary={self.MULTIPART_BOUNDARY}")
            return self.create_request_content(method, path, parsed_url.netloc, headers, self._join_params(body_params, marked_param), self.FORM_URLENCODED)

        new_nodes.extend(self._create_action_nodes(source_key, method, None, None, query_params + (body_params or []), create_request, known_nodes, respect_param_values))
        return new_nodes


    def parse_url_list_to_nodes(self, urls: list[dict], headers: dict | str = None, known_nodes: list = None, respect_param_values: bool = False, forms: list[dict] = None) -> list[dict]:
        """
        Parses a list of requests and forms into their separate components and returns them as a list of nodes.

        Args:
            urls (list[dict]): A list of requests, each with the keys "url", "method", "statusCode" and optionally
                "data" and "contentType" (or "ContentType").
            headers (dict | str, optional): The HTTP headers shared by all the requests, as a dictionary or separated by \\r\\n. Defaults to None.
            known_nodes (list, optional): A list of known nodes. If provided, the function filters out nodes
                that already exist in this list. Defaults to None.
            respect_param_values (bool, optional): If True, requests that differ only in parameter values are
                separate actions. If False, they are considered duplicates. Defaults to False.
            forms (list[dict], optional): A list of HTML forms as described in parse_form_to_nodes. Defaults to None.

        Returns:
            list[dict]: A list of node dictionaries representing the requests and forms.

        Note:
            This function parses each of the requests using the parse_url_to_nodes method and then each of the forms
            using the parse_form_to_nodes method, so a form never replaces an action that was requested. It extends
            the list of known_nodes with the parsed nodes. If known_nodes is not provided, a new list is used.
        """

        known_nodes = known_nodes or []
        assert isinstance(known_nodes, list)
        for item in urls:
            content_type = item.get("contentType") or item.get("ContentType")
            known_nodes.extend(self.parse_url_to_nodes(item["url"], item["method"], item["statusCode"], item.get("data"), headers, known_nodes, respect_param_values, content_type))
        for form in forms or []:
            known_nodes.extend(self.parse_form_to_nodes(form, headers, known_nodes, respect_param_values))
        return known_nodes


    def create_request_content(self, method: str, path: str, domain: str, headers: dict | str = None, data: str = None, content_type: str = None) -> str:
        """
        Creates the text of an HTTP request.

        Args:
            method (str): The HTTP method of the request.
            path (str): The path of the request, including its query parameters.
            domain (str): The value of the Host header.
            headers (dict | str, optional): The HTTP headers of the request, as a dictionary or separated by \\r\\n. Defaults to None.
            data (str, optional): The body of the request. Defaults to None.
            content_type (str, optional): The Content-Type of the body, which replaces the one in headers.
                If neither is given, application/x-www-form-urlencoded is used. Defaults to None.

        Returns:
            str: The text of the HTTP request.

        Note:
            Host, Content-Length and Connection are always generated, so they are left out of the given headers.
        """

        skipped_headers = self.GENERATED_HEADERS | ({"content-type"} if content_type else set())
        header_lines = [line for line in self._get_header_lines(headers) if self._get_header_name(line) not in skipped_headers]

        request_content = f"{method} {path} HTTP/1.1\r\n"
        request_content += f"Host: {domain}\r\n"
        request_content += "".join(f"{line}\r\n" for line in header_lines)
        if data is not None:
            if content_type or "content-type" not in [self._get_header_name(line) for line in header_lines]:
                request_content += f"Content-Type: {content_type or self.FORM_URLENCODED}\r\n"
            request_content += f"Content-Length: {len(data.encode())}\r\n"
        request_content += "Connection: close\r\n\r\n"
        if data is not None:
            request_content += data
        return request_content


    def get_input_type(self, value: str, name: str = None, form_type: str = None, default: str = "String") -> str | None:
        """
        Determines the input type of a parameter.

        Args:
            value (str): The URL decoded parameter value.
            name (str, optional): The URL decoded parameter name. Defaults to None.
            form_type (str, optional): The input type passed with a form. Defaults to None.
            default (str, optional): The input type (without the webInputType prefix) of an empty value that neither
                the form type nor the name determines. Defaults to "String".

        Returns:
            str | None: The webInputType code, i.e. webInputType followed by one of Boolean, Integer, Float, String, Password,
                Email, Username, Token, Hash, Crypted, CsrfToken, Phone, Date, Datetime, Time, SessionId, IpAddress, Url,
                Filename, Guid, Path, Json, Array, Xml, SerializedData or Captcha, or None if the default is None.

        Note:
            The input type passed with a form is used first, then the type of the value. String and empty values
            are further distinguished by the name of the parameter.
        """

        input_type = self._get_input_type_by_form_type(form_type, value) or self._get_input_type_by_value(value)
        if input_type in (None, "String") and name:
            input_type = self._get_input_type_by_name(name) or input_type
        input_type = input_type or default
        return f"webInputType{input_type}" if input_type else None


    def get_response_type(self, content_type: str) -> str | None:
        """
        Converts the Content-Type of a response to webActionResponseType.

        Args:
            content_type (str): The Content-Type of the response, e.g. "text/html; charset=utf-8".

        Returns:
            str | None: The webActionResponseType, e.g. webActionResponseTypeHtml, or None if no content type is given.
        """

        mime_type = (content_type or "").split(";")[0].strip().lower()
        if not mime_type:
            return None
        suffix = self.RESPONSE_TYPES.get(mime_type)
        if not suffix:
            if mime_type.startswith("image/"):
                suffix = "Image"
            elif mime_type.startswith(self.DOCUMENT_TYPE_PREFIXES):
                suffix = "Document"
            elif mime_type.endswith("+json"):
                suffix = "Json"
            elif mime_type.endswith("+xml"):
                suffix = "Xml"
            else:
                suffix = "Other"
        return f"webActionResponseType{suffix}"


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

    def _create_action_nodes(self, source_key: str, method: str, status_code: str, content_type: str, params: list[_Param], create_request, known_nodes: list, respect_param_values: bool) -> list[dict]:
        """Returns the action node and its webInput nodes, or nothing if the source already has the action. create_request(param) marks the param."""
        action_name = " ".join(filter(None, [method, "&".join(param.raw for param in params)]))
        if self._is_known_action(source_key, action_name, known_nodes, respect_param_values):
            return []

        action_properties = {
            "name": action_name,
            "webHttpMethod": f"webHttpMethod{method.capitalize()}",
            "webActionStatusCode": None if status_code is None else f"webActionStatusCode{status_code}",
            "webActionResponseType": self.get_response_type(content_type),
            "webActionRequest": create_request(),
        }
        action_node = self.ptjsonlib.create_node_object("webPageAction", None, source_key, action_properties)
        nodes = [action_node]
        for param in params:
            input_properties = {
                "name": param.name,
                "webInputType": self.get_input_type(param.value, param.name, param.form_type, param.default_type),
                "is_required": param.required,
                "webActionRequest": create_request(param),
            }
            nodes.append(self.ptjsonlib.create_node_object("webInput", None, action_node["key"], input_properties))
        return nodes

    def _is_known_action(self, source_key: str, action_name: str, known_nodes: list, respect_param_values: bool) -> bool:
        """Returns True if the source already has this action. Checked here because node_duplicity_check ignores the parent."""
        action_id = self._get_action_id(action_name, respect_param_values)
        for node in known_nodes:
            if node["type"] == "webPageAction" and node["parent"] == source_key:
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

    def _parse_params(self, params: str, default_type: str = None) -> list[_Param]:
        """Returns the parameters of the given query or urlencoded POST data, typed as default_type when nothing else tells"""
        parsed_params = []
        for raw in self._split_params(params):
            raw_name, _, raw_value = raw.partition("=")
            parsed_params.append(_Param(raw, raw_name, unquote(raw_name), unquote(raw_value), default_type=default_type))
        return parsed_params

    def _create_form_param(self, parameter: dict) -> _Param:
        """Returns the parameter of the given form field"""
        name = str(parameter.get("name") or "")
        value = parameter.get("value")
        value = "" if value is None else str(value)
        raw_name = quote_plus(name)
        return _Param(f"{raw_name}={quote_plus(value)}", raw_name, name, value, parameter.get("type"), bool(parameter.get("required")))

    def _join_params(self, params: list[_Param], marked_param: _Param = None) -> str:
        """Returns the parameters joined back together, with the value of marked_param replaced by the placeholder"""
        return "&".join(f"{param.raw_name}={self.INPUT_PLACEHOLDER}" if param is marked_param else param.raw for param in params)

    def _create_multipart_body(self, params: list[_Param], marked_param: _Param = None) -> str:
        """Returns the multipart/form-data body of the parameters, with the value (or file name) of marked_param replaced by the placeholder"""
        body = ""
        for param in params:
            value = self.INPUT_PLACEHOLDER if param is marked_param else param.value
            body += f"--{self.MULTIPART_BOUNDARY}\r\n"
            if (param.form_type or "").lower() == "file":
                body += f'Content-Disposition: form-data; name="{self._escape_multipart(param.name)}"; filename="{self._escape_multipart(value)}"\r\n'
                body += "Content-Type: application/octet-stream\r\n\r\n\r\n"
            else:
                body += f'Content-Disposition: form-data; name="{self._escape_multipart(param.name)}"\r\n\r\n{value}\r\n'
        return body + f"--{self.MULTIPART_BOUNDARY}--\r\n"

    def _escape_multipart(self, text: str) -> str:
        """Escapes a name or file name in Content-Disposition like browsers do"""
        return text.replace("\r", "%0D").replace("\n", "%0A").replace('"', "%22")

    def _get_request_path(self, parsed_url, query: str) -> str:
        """Returns the path of the parsed url with the given query string"""
        return urlunparse(("", "", parsed_url.path or "/", "", query, ""))

    def _get_header_lines(self, headers: dict | str) -> list[str]:
        """Returns the given headers as a list of "Name: value" lines"""
        if not headers:
            return []
        if isinstance(headers, str):
            return [line for line in headers.splitlines() if line.strip()]
        return [f"{name}: {value}" for name, value in headers.items()]

    def _get_header_name(self, header_line: str) -> str:
        """Returns the lowercase name of the given header line"""
        return header_line.partition(":")[0].strip().lower()

    def _get_input_type_by_form_type(self, form_type: str, value: str) -> str | None:
        """Returns the input type of the form field type, or None if the field type does not tell (e.g. string, hidden or select)"""
        input_type = self.FORM_INPUT_TYPES.get((form_type or "").lower())
        if input_type == "Integer" and re.fullmatch(self.FLOAT_PATTERN, value):
            return "Float"
        return input_type

    def _get_input_type_by_value(self, value: str) -> str | None:
        """Returns the input type of the value, or None for an empty value. The order of the checks matters, e.g. +420777123456 would also pass as an integer."""
        if not value:
            return None
        if value.lower() in self.BOOLEAN_VALUES:
            return "Boolean"
        json_type = self._get_json_type(value)
        if json_type:
            return json_type
        if self._is_xml(value):
            return "Xml"
        if self._is_serialized(value):
            return "SerializedData"
        if len(value) in self.HASH_LENGTHS and re.fullmatch(r"[0-9a-fA-F]+", value):
            return "Hash"
        if is_valid_ip_address(value):
            return "IpAddress"
        if self._is_phone(value):
            return "Phone"
        if re.fullmatch(r"[+-]?[0-9]+", value):
            return "Integer"
        if re.fullmatch(self.FLOAT_PATTERN, value):
            return "Float"
        if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.\-]*://\S+|//\S+|www\.\S+", value):
            return "Url"
        if re.fullmatch(r"[^@\s:/]+@[^@\s:/]+\.[^@\s:/.]+", value):
            return "Email"
        if self._is_filename(value):
            return "Filename"
        if self._decode_base64(value) is not None:
            return "Crypted"
        return "String"

    def _get_input_type_by_name(self, name: str) -> str | None:
        """Returns the input type of a parameter by its name, or None if the name does not tell"""
        name = name.lower()
        for keywords, input_type in self.NAME_INPUT_TYPES:
            if any(keyword.lower() in name for keyword in keywords):
                return input_type
        return None

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

    def _get_json_type(self, value: str) -> str | None:
        """Returns Json for a JSON object, Array for a JSON array, or None"""
        if not value.lstrip().startswith(("{", "[")):
            return None
        try:
            data = json.loads(value)
        except (ValueError, RecursionError):
            return None
        if isinstance(data, dict):
            return "Json"
        if isinstance(data, list):
            return "Array"
        return None

    def _is_xml(self, value: str) -> bool:
        """Returns True for a well-formed XML element. Values with a DOCTYPE or an ENTITY declaration are XML, but are not parsed."""
        value = value.strip()
        if not (value.startswith("<") and value.endswith(">")):
            return False
        if re.search(r"<!(?:DOCTYPE|ENTITY)", value, re.IGNORECASE):
            return True
        try:
            ElementTree.fromstring(value)
            return True
        except (ElementTree.ParseError, ValueError):
            return False

    def _is_serialized(self, value: str) -> bool:
        """Returns True for PHP serialized data, or for Java, .NET (including ViewState) or Python pickle serialized data in hex or base64"""
        if re.fullmatch(self.PHP_SERIALIZED_PATTERN, value, re.DOTALL):
            return True
        if len(value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", value):
            data = bytes.fromhex(value)
        else:
            data = self._decode_base64(value)
        return bool(data) and data.startswith(self.SERIALIZED_SIGNATURES)

    def _decode_base64(self, value: str) -> bytes | None:
        """Returns the decoded non-empty base64 value, or None if it is empty or cannot be decoded as base64"""
        if not value:
            return None
        try:
            return base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return None
