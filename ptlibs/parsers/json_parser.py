class JsonParser():
    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

    def parse_to_nodes(self, json_data: str|dict):
        """Parse JSON to nodes"""
        result_nodes = []
        try:
            json_data = json.loads(json_data)
            nodes = self.traverse_json(json_data)
            return result_nodes
        except Exception as e:
            print(e)

    def traverse_json(self, data, parent_id=None, parent_key=None):
        nodes = []
        # Create a node for the current data
        if isinstance(data, dict):
            # Create a root or start node based on the parent_id
            node = self.ptjsonlib.create_node_object(node_type="root" if parent_id is None else "dictionary", parent=parent_id)
            if parent_key:
                node["properties"].update({"key": parent_key})
            for key, value in data.items():
                # Traverse the nested structures and pass the current key as parent_key
                child_nodes = self.traverse_json(value, parent_id=node["key"], parent_key=key)
                # Extend the nodes with child nodes
                nodes.extend(child_nodes)
            # Append the current node to the nodes list
            nodes.append(node)

        elif isinstance(data, list):
            node = self.ptjsonlib.create_node_object(node_type="list", parent=parent_id)
            if parent_key:
                node["properties"].update({"key": parent_key})
            for index, item in enumerate(data):
                child_nodes = self.traverse_json(item, parent_id=node["key"])
                nodes.extend(child_nodes)
            nodes.append(node)
        else:
            # Create a node for a simple value, including the key
            node = self.ptjsonlib.create_node_object("leaf", properties={"key": parent_key, "value": data})
            node["parent"] = parent_id  # Set the parent ID

            nodes.append(node)

        nodes = sorted(nodes, key=lambda x: x['type'])
        return nodes