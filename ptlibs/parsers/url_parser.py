from ptlibs.ptpathtypedetector import PtPathTypeDetector

class UrlParser():
    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

    def parse_url_to_nodes(self, url: str, known_nodes: list = None) -> list[dict]:
        """
        Parses the given URL into its separate components and returns them as a list of nodes.

        Args:
            url (str): The URL to parse.
            known_nodes (list, optional): A list of known nodes. If provided, the function returns only nodes
                that are not included in this list. Defaults to None.

        Returns:
            list[dict]: A list of node dictionaries representing the URL parts.

        Note:
            This function parses the URL into its components and constructs node dictionaries for each part.
            If known_nodes is passed, it filters out nodes that already exist in the known_nodes list.
        """

        new_nodes = []
        known_nodes = known_nodes or []
        base_url = self.get_base_url(url)
        parent = None
        paths = self.get_paths(url)
        for index, path in enumerate(paths):
            url = f"{base_url}/{'/'.join(paths[0:index+1])}"
            page_type = PtPathTypeDetector().get_type(path)
            parent_type = "webRootDirectory" if index == 0 else None
            properties = {"name": path, "url": url, "webSourceType": page_type}
            node_object = self.ptjsonlib.create_node_object("webSource", parent_type, parent, properties, new_nodes, known_nodes)
            if type(node_object) is not str: # check whether node already exists
                parent = node_object["key"]
                new_nodes.append(node_object)
            else:
                parent = node_object
        return new_nodes


    def parse_url_list_to_nodes(self, url_list: list, known_nodes: list = None) -> list[dict]:
        """
        Parses a list of URLs into their separate components and returns them as a list of nodes.

        Args:
            url_list (list): A list of URLs to parse.
            known_nodes (list, optional): A list of known nodes. If provided, the function filters out nodes
                that already exist in this list. Defaults to None.

        Returns:
            list[dict]: A list of node dictionaries representing the URL parts.

        Note:
            This function iterates through the list of URLs and parses each URL into its components using the parse_url2nodes
            method. It then extends the list of known_nodes with the parsed nodes. If known_nodes is not provided, a new list is used.
        """

        known_nodes = known_nodes or []
        assert isinstance(known_nodes, list)
        for url in url_list:
            known_nodes.extend(self.parse_url_to_nodes(url, known_nodes))
        return known_nodes