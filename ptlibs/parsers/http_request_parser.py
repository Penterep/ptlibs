"""This module contains functions used for parsing http requests."""
import urllib
import json

from ptlibs.parsers.json_parser import JsonParser
from ptlibs.parsers.xml_parser import XmlParser

class HttpRequestParser():
    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

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
                    print("RDATA:", request_data)
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

    def get_request_headers(self, http_request):
        request_headers, _, _ = http_request.partition("\n\n")
        request_headers = [line.split(": ", 1) for line in request_headers.split("\n")[1:] if ": " in line]
        return request_headers

    def get_request_data(self, http_request):
        _, _, request_data = http_request.partition("\n\n")
        return request_data