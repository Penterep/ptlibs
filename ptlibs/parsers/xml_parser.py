import xml.etree.ElementTree as ET

class XmlParser():
    def __init__(self, ptjsonlib: object):
        self.ptjsonlib = ptjsonlib

    def parse_to_nodes(self, request_data):
        result_nodes = []
        try:
            xml_data = ET.fromstring(request_data)
            result_nodes.extend(self.traverse_xml(xml_data))
        except Exception as e:
            pass

        return result_nodes

    def traverse_xml(self, element, parent_id=None, parent_key=None):
        nodes = []
        node = self.ptjsonlib.create_node_object("xml_root" if parent_id is None else "xml_child", parent=parent_id)

        # Add element tag to properties
        node["properties"].update({"tag": element.tag})

         # If the element has text content, add it to properties
        if element.text and element.text.strip():
            node["properties"].update({"text": element.text.strip()})

        nodes.append(node)

        # Recursively process child elements
        for child in element:
            child_nodes = self.traverse_xml(child, parent_id=node["key"], parent_key=child.tag)
            nodes.extend(child_nodes)

        return nodes