import json
import sys
import uuid

from ptlibs.ptprinthelper import out_if, out_ifnot, ptprint
from ptlibs.ptpathtypedetector import PtPathTypeDetector


class PtJsonLib:
    def __init__(self, guid: str = "", status: str = "", satid: str = "") -> None:
        self.PtPathTypeDetector = PtPathTypeDetector()
        self.json_object = {
            "satid": satid,
            "guid": guid,
            "status": status,
            "message": "",
            "results": {
                "nodes": [],
                "properties": {},
                "vulnerabilities": []
            }
        }

    def set_guid(self, guid: str) -> None:
        self.json_object["guid"] = guid

    def add_node(self, node_object: dict) -> None:
        """Adds node to json_object"""
        assert type(node_object) is dict
        self.json_object["results"]["nodes"].append(node_object)

    def add_nodes(self, nodes: list) -> None:
        """Adds nodes to json_object"""
        assert type(nodes) is list
        for node in nodes:
            self.add_node(node)

    def parse_url2nodes(self, url: str, nodes: list = None) -> list[dict]:
        """Parses url to node object"""
        nodes = nodes if nodes else []
        base_url = self.get_base_url(url)
        parent = None
        paths = self.get_paths(url)
        for index, path in enumerate(paths):
            url = f"{base_url}/{'/'.join(paths[0:index+1])}"
            page_type = self.PtPathTypeDetector.get_type(path)
            parent_type = "webRootDirectory" if index == 0 else None
            properties = {"name": path, "url": url, "webSourceType": page_type}
            node_object = self.create_node_object("webSource", parent_type, parent, properties, nodes)
            if type(node_object) is not str: # check whether node already exists
                parent = node_object["key"]
                nodes.append(node_object)
            else:
                parent = node_object
        return nodes

    def get_base_url(self, url: str) -> str:
        """Returns base url"""
        schema_separator = "://"
        schema_split = url.split(schema_separator)
        schema = schema_split[0] if len(schema_split) > 1 else ""
        address = schema_split[-1]
        base_address = address.split("/")[0]
        return f"{schema + schema_separator if schema else ''}{base_address}"

    def get_paths(self, url: str) -> list[str]:
        """Returns paths from url"""
        return url.strip("/").split("/")[2:][1:]

    def create_node_object(self, node_type: str, parent_type=None, parent=None, properties: dict = None, nodes: list = None, vulnerabilities: list = None) -> dict:
        """Creates node object"""
        properties = properties or {}
        nodes = nodes or []
        vulnerabilities = vulnerabilities or []
        assert isinstance(properties, dict)
        assert isinstance(nodes, list)
        assert isinstance(vulnerabilities, list)

        ident = self.node_duplicity_check(parent_type, properties, nodes)
        if ident:
            return ident
        return {"type": node_type, "key": self.create_guid(), "parent": parent, "parentType": parent_type, "properties": properties, "vulnerabilities": vulnerabilities }

    def node_duplicity_check(self, parent_type, properties: dict, nodes: list) -> str | None:
        """Returns node ident if node already exists in json_object else returns None"""
        for node in nodes:
            if node["parentType"] == parent_type:
                if node["properties"] == properties:
                    return node["key"]
        return None

    def create_guid(self) -> str:
        """Creates random guid"""
        return str(uuid.uuid4())

    def to_camel_case(self, snake_str):
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])

    def convert_keys_to_camel_case(self, original_dict: dict, keys_to_convert: list):
        """Create a new dictionary with camelCase keys"""
        camel_case_dict = {}
        for key, value in original_dict.items():
            if key in keys_to_convert:
                camel_case_key = self.to_camel_case(key)
                camel_case_dict[camel_case_key] = value
            else:
                camel_case_dict[key] = value
        return camel_case_dict

    def add_property(self, name: str, value: str) -> None:
        self.json_object["results"]["properties"].update({"name": name, "value": value})

    def add_vulnerability(self, vuln_code: str, vuln_request: str=None, vuln_response: str=None, description: str=None, score: str=None, note: str=None, node_key: str=None) -> None:
        """Add vulnerability code to the json result, if <node_key> parameter is provided, vulnerability will be added to the specified node instead."""
        vulnerability_dict = {k:v for k, v in locals().items() if v is not None}; vulnerability_dict.pop("self", None)
        vulnerability_dict = self.convert_keys_to_camel_case(vulnerability_dict, keys_to_convert=["vuln_code", "vuln_request", "vuln_response"])

        if node_key:
            vulnerability_dict.pop("node_key")
            for d in self.json_object["results"]["nodes"]:
                if d["key"] == node_key:
                    if not self.vuln_code_in_vulnerabilities(vuln_code):
                        d["vulnerabilities"].append(vulnerability_dict)
                    break
        else:
            self.json_object["results"]["vulnerabilities"].append(vulnerability_dict)

    def vuln_code_in_vulnerabilities(self, code: str) -> bool:
        for obj in self.json_object["results"]["vulnerabilities"]:
            if obj.get("code") == code:
                return True

    def set_status(self, status: str, message: str = "") -> None:
        self.json_object["status"] = status
        if message:
            self.json_object["message"] = message

    def set_message(self, message: str) -> None:
        self.json_object["message"] = message

    def get_result_json(self) -> str:
        return json.dumps(self.json_object, indent=4)

    def end_error(self, message, condition):
        ptprint( out_ifnot(f"Error: {message}", "ERROR", condition) )
        self.set_status("error", message)
        ptprint( out_if(self.get_result_json(), None, condition) )
        sys.exit(1)

    def end_ok(self, message, condition, bullet_type="ERROR"):
        ptprint( out_ifnot(message, bullet_type, condition) )
        self.set_status("ok", message)
        ptprint( out_if(self.get_result_json(), None, condition) )
        sys.exit(0)
