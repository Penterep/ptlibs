"""This module contains functions used for marking injection points in http requests."""
from typing import Tuple, Dict, Any, List, Iterable, Dict
import re
from ptlibs import ptprinthelper, ptmisclib, ptjsonlib, ptnethelper, ptcharsethelper
from ptlibs.parsers.http_request_parser import HttpRequestParser
from urllib.parse import urlparse, urlunparse, ParseResult


class HttpRequestFileMarker():
    def __init__(self, http_request_parser: HttpRequestParser = HttpRequestParser(ptjsonlib=ptjsonlib.PtJsonLib(), use_json=False, placeholder= "<INJECT_HERE>")):
        self.request_parser = http_request_parser
        self.placeholder = http_request_parser.placeholder

        # selected headers which are not marked for injection by default.
        self.header_skip_set = {
            'Accept-Encoding', 'Access-Control-Request-Headers', 'Access-Control-Request-Method', 'Allow', 'Authorization',
            'CSRFToken', 'Cache-Control', 'Connection', 'Content-Digest', 'Content-Encoding', 'Content-Length',
            'Content-MD5', 'Content-Security-Policy', 'Content-Type', 'Front-End-Https', 'HTTP2-Settings',
            'If-Match', 'If-Modified-Since', 'If-None-Match',    'If-Range', 'If-Unmodified-Since', 'Max-Forwards',
            'Pragma', 'Proxy-Authorization', 'Save-Data', 'Sec-GPC', 'Sec-WebSocket-Key', 'TE', 'Transfer-Encoding',
            'Upgrade', 'Upgrade-Insecure-Requests', 'X-Csrf-Token', 'X-UIDH', 'X-XSRF-TOKEN', 'status'
        }
        # headers for which the value is not replaced entirely but only appended
        self.header_append_set = {}


    def iterate_mark(self, http_request: str, parameter: str = 0) -> Iterable[Tuple[str, Dict[str, Any]]]:
        """
        Creates an iterator returning a tuple of injection point name and http request dictionary with some part marked with placeholder.

        Provides marking for headers and request bodies of types:
            text/plain
            application/x-www-form-urlencoded
            multipart/form-data
            application/json
            application/xml

        Parameters:
            - http_request: The HTTP request string to mark.
            - parameter: to mark only that parameter in URL encoded data (mutually exclusive with explicit marker)

        Returns:
            - An Iterator of name, marked http request dictionary pairs
        """
        url, method, headers, request_data = self.request_parser.parse_http_request(http_request)
        request_parse                           = dict()
        request_parse['url']                   = url
        request_parse['method']           = method
        request_parse['headers']           = headers
        request_parse['data']                 = request_data

        if self.placeholder in http_request and parameter:
            raise ValueError(f"Specifying parameter and specifying manually with {self.placeholder} are mutually exclusive.")

        if self.placeholder in http_request:
            yield "Manually marked", request_parse
            return

        if 'Content-Length' in headers.keys():
            del headers['Content-Length'] # since the size of data will change after payload injection it should be reset

        for name, marked_header in self.iterate_mark_headers(headers):
            result = request_parse.copy()
            result["headers"] = marked_header
            yield name, result


        if method == 'GET':
            parsed_url = urlparse(url)
            for name, marked_query in self.iterate_mark_url_encoded(parsed_url.query, parameter):
                newurl = urlunparse(ParseResult(
                    parsed_url.scheme, parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    marked_query,
                    parsed_url.fragment)
                )
                result = request_parse.copy()
                result['url'] = newurl
                yield name, result
            return

        content_type = headers.get('Content-Type', None)
        if not content_type:
            return

        if "text/plain" in content_type:
            result = request_parse.copy()
            result['data'] = self.placeholder
            yield ("plain text body", (headers, placeholder))

        elif "application/x-www-form-urlencoded" in content_type:
            for name, marked in self.iterate_mark_url_encoded(request_parse['data'], parameter):
                result = request_parse.copy()
                result['data'] = marked
                yield name, result

        elif 'application/json' in content_type or 'text/json':
            for name, marked in self.iterate_mark_json(request_parse['data']):
                result = request_parse.copy()
                result['data'] = marked
                yield name, result

        elif 'application/xml' in content_type or 'text/xml' in content_type:
            for name, marked in self.iterate_mark_xml(request_parse['data']):
                result = request_parse.copy()
                result['data'] = marked
                yield name, result

        elif 'multipart/form-data' in content_type:
            for name, marked in self.iterate_mark_xml(request_parse['data']):
                result = request_parse.copy()
                result['data'] = marked
                yield name, result

        return


    def iterate_mark_strings(self, http_request, parameter: str = None) -> Iterable[Tuple[str, str]]:
        """
        Same as self.iterate_mark but outputs the requests in str
        """

        for name, http_request in self.iterate_mark(http_request, parameter):
            result = self.request_parser.build_request(
                url=http_request['url'],
                headers=http_request['headers'],
                request_data=http_request['data'],
                method=http_request['method']
            )
            yield name, result


    def fill_payload(http_request: str | Dict[str, str], payload: str) -> str:
        """
        Injects payload into the request at markted site
        Parameters:
            - http_request:     The HTTP request string or dictionary produced by HttpRequestParser.parse_http_request to mark.
            - payload:             string payload to insert
        Returns:
            - string representation of prepared HTTP request
        """

        if isinstance(http_request, dict):
            http_request = self.request_parser.build_request(
                url=http_request['url'],
                headers=http_request['headers'],
                request_data=http_request['data'],
                method=http_request['method']
            )
        elif not isinstance(http_request, str):
            raise TypeError("http_request must be an instance of either dict or str")

        result = http_request.replace(self.placeholder, payload)

        return result


    ### Rest of the class are helper methods


    def iterate_mark_json(self, json_str: str) -> Iterable[Tuple[str, str]]:
        """
        Creates iterator returning names, json with marked injection points.
        Parameters:
            - json_str: json in string
        Returns:
            Iterable of tuples of names and marked json strings
        """

        # json_mark_regex_str = '((\\"([\\w\\s(\\\\\\")]|[\\s])+\\"))|(true|false|null|\\d+\\.?\\d*)'
        json_mark_regex_str = r'\"[^\"]*\"|\d+\.?\d*|true|false|null'
        rg = re.compile(json_mark_regex_str)
        for m in rg.finditer(json_str):
            start = m.start()
            value = m.group()
            affix = '"'
            yield self.body_var_name(start, value), self.affixed_replace(start, value, json_str, affix, affix, self.placeholder)


    def iterate_mark_xml(self, xml_str: str) -> Iterable[Tuple[str, str]]:
        """
        Creates iterator returning xml string with marked injection points.
        Parameters:
            - xml_str: xml in string
        Returns:
            Iterable of tuples of names and marked xml strings
        """
        xml_mark_regex = '(>.*</)|(\\"[^\\"]*\\")'
        rg = re.compile(xml_mark_regex)
        for m in rg.finditer(xml_str):
            start = m.start()
            value = m.group()
            prefix, suffix = "", ""
            if xml_str[start] == ">":
                prefix, suffix = ">", "</"
            elif xml_str[start] == "'":
                prefix, suffix = "'", "'"
            elif xml_str[start] == '"':
                prefix, suffix = '"', '"'
            yield self.body_var_name(start, value), self.affixed_replace(start, value, xml_str, prefix, suffix, self.placeholder)


    def iterate_mark_url_encoded(self, url_string: str, parameter: str = None) -> Iterable[Tuple[str, str]]:
        """
        Creates iterator returning marked injection points in url encoded strings
        Parameters:
            - url_string: url encoded data
            - parameter: optional parameter to select
        Returns:
             Iterable of tuples of names and marked url coded data strings
        """
        url_regex = None
        if parameter and parameter not in url_string:
            raise ValueError(f"Provided parameter {str(parameter)} not in found.")
        if parameter:
            url_regex = f"{parameter}=.*?(&|$)"
        else:
            url_regex = "[\\w\\d]+=.*?(&|$)"
        rg = re.compile(url_regex)

        for m in rg.finditer(url_string):
            start = m.start()
            value = m.group()
            suffix = None
            if value and value[-1] == '&':
                suffix = '&'
            else:
                suffix = ''

            name, argument = None, None

            if parameter:
                name = parameter
            else:
                name, argument = value.split('=')
                argument = argument.removesuffix('&')

            yield name, self.affixed_replace(start, value, url_string, name + '=', suffix, self.placeholder)


    def iterate_mark_multipart(self, body: str) -> Iterable[Tuple[str, str]]:
        """
        Creates iterator returning marked injection points for application/multipart bodies
        Parameters:
            - body: the string of http request body
        Returns:
            Iterable of tuples of names and marked bodies
        """
        boundary = body[:body.find('\n')].rstrip()
        headers_rg_str = r'\s*(\w+\-\w+:)\s*[\w\-/]+(;\s*[\w\-]+=\".*?\")*'
        parts = body.split(boundary)
        parsed_parts = []


        def cleanup_parts(parts):
            if parts:
                if parts[0] =='':
                    parts.pop(0)
                if parts[-1] == '--':
                    parts.pop(-1)


        def split_headers_from_body(part: str):
            stripped, rest = strip_if_prefix(part, headers_rg_str)
            rest = rest.lstrip()
            return stripped, rest

        unmodified = []
        work_copy = []

        cleanup_parts(parts)

        for part in parts:
            unmodified.append(split_headers_from_body(part))


        def mark_part(part_tuple: Tuple[str, str], placeholder: str) -> Tuple[str, Tuple[str, str]]:
            headers, body = part_tuple

            if 'text/plain' in headers or 'Content-Type' not in headers:
                t = ("plain text body", (headers, placeholder))
                yield t
            elif 'application/x-www-form-urlencoded' in headers:
                for name, marked_body in self.iterate_mark_url_encoded(body):
                    yield (name, (headers, marked_body))
            elif any(T in headers for T in ('text/xml', 'application/xml', 'text/html')):
                for name, marked_body in self.iterate_mark_xml(body):
                    yield (name, (headers, marked_body))
            elif 'application/json' in headers or 'text/json' in headers:
                for name, marked_body in self.iterate_mark_json(body):
                    yield (name, (headers, marked_body))
            elif 'multipart/form-data' in headers:
                for name, marked_body in self.iterate_mark_multipart(body):
                    yield (name, (headers, marked_body))


        def unparse_parts(parts: List[Tuple[str, str]], boundary: str) -> str:
            result = [boundary + '\n' + part[0] + "\n\n" + part[1] for part in parts]
            return "".join(result) + f'{boundary}--'


        for i in range(len(unmodified)):
            work_copy = [v for v in unmodified]
            for name, marked in mark_part(unmodified[i], self.placeholder):
                work_copy[i] = marked
                yield name, unparse_parts(work_copy, boundary)


    def iterate_mark_headers(self, headers: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        """
        Creates iterator returning marked injection points for request headers
        Parameters:
            - headers: dictionary of HTTP headers
        Returns:
            Iterable of dictionaries with marked values
        """
        for k, v in headers.items():
            headers_copy = headers.copy()

            if k in self.header_skip_set:
                continue
            elif k in self.header_append_set:
                headers_copy[k] = headers_copy[k] + self.placeholder
            else:
                headers_copy[k] = self.placeholder

            yield k, headers_copy


    def body_var_name(self, start: int, value: str) -> str:
        """
        Creates name for non-parameter based injection points.
        Parameters:
            - start: index of where in body the payload starts
            - value: string being replaced
        Returns:
            - Generated name for injection point
        """
        return "".join(("body: ", value, f" at offset {start + len(value)}"))


    def affixed_replace(self, start: int, value: str, string: str, prefix: str, suffix: str, new_value: str)  -> str:
        """
        Helper to replace a value provding prefix and suffix
        Replace value starting at start with new_value with affices prefix and suffix.
        Parameters:
            - start: the start offset of value
            - value: value to be replaced
            - string: in which the replecing is done
            - prefix: prefix for new_value
            -suffix: suffix for new value
            -new_value: new value
        Returns:
            - String with new_value in place of value
        """
        return "".join((string[:start], prefix, new_value, suffix, string[start + len(value):]))


    def strip_if_prefix(self, string: str, regex: str) -> Tuple[str, str]:
        """
        Splits string into its prefix match and the rest
        Parameters:
            - string: which is to be split
            - regex: defining the wanted prefix
        Returns:
            - Tuple matched prefix(or '), rest of string
        """
        rg = re.compile(rf'^{regex}')
        m = rg.match(string)
        if m:
            return m.group(), string[len(m.group()):]
        else:
            return "", string


    def mark_iterate_variables(self, data: str) -> Iterable[Tuple[str, str]]:
        """
        Iterate over variables of the form name="value"; name2="value2"
        """
        var_rg = re.compile(r'[\w\-0-9]+=\"[^\"]*\"')
        for m in var_rg.finditer(data):
            start = m.start()
            value = m.group()
            name, key = value.split("=")
            yield name, affixed_replace(start, value, data, name + '="', '"', self.placeholder)
