"""Module containing the BloQCat Framework endpoint(s) of the v1 API."""

from flask import request
from flask.views import MethodView
from http import HTTPStatus
from flask import Response

from .root import API_V1

import xml.etree.ElementTree as ET
import requests


@API_V1.route("/bloqcat/winery/topology/deploy/json", methods=["POST"])
class TopologyView(MethodView):
    """POST endpoint to retrieve the aggregated solution."""

    def post(self):
        # Parse the JSON topology file from the request body
        try:
            data = request.json
        except ET.ParseError as e:
            return f"Invalid JSON data: {str(e)}", HTTPStatus.BAD_REQUEST

        # Validation of the data
        valid, message = self.validate_data(data)
        if not valid:
            return message, HTTPStatus.BAD_REQUEST

        # Process the topology
        nodes = data.get("nodeTemplates", [])
        relationships = data.get("relationshipTemplates", [])

        valid_path, message_path = self.validate_path(nodes, relationships)
        if not valid_path:
            return message_path, HTTPStatus.BAD_REQUEST

        solution_nodes, solution_relationships = self.create_solution_path(
            nodes, relationships
        )

        concrete_solution_files = self.fetch_files(solution_nodes)

        if not concrete_solution_files:
            return "Error retrieving files.", HTTPStatus.BAD_REQUEST

        # Aggregating the files
        file_content = self.aggregate_concrete_solution_files(
            concrete_solution_files, solution_nodes, solution_relationships
        )

        # Create the file content (after successful validation)
        # file_content = self.create_file_content(data)

        # Create a response with the file content
        response = Response(
            file_content,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment;filename=aggregation.qasm"},
        )

        return response

    def extract_cs(self, input_text):
        lines = input_text.split("\n")
        start_index = None
        end_index = None

        # Find the index of the line containing 'creg' and 'measure'
        for i, line in enumerate(lines):
            if "creg" in line and start_index is None:
                start_index = i + 1
            if "measure" in line and end_index is None:
                end_index = i
                break

        # Check if both 'creg' and 'measure' were found
        if start_index is not None and end_index is not None:
            return "\n".join(lines[start_index:end_index])
        else:
            return "Unable to find the required sections."

    def fetch_files(self, solution_nodes):
        files_content = []
        for node_id in solution_nodes.keys():
            file_content = self.fetch_file_content(node_id)
            if file_content:
                files_content.append(file_content)
                # Here we print the contents of each file
                print(f"Contents of the file for Node ID {node_id}:")
                print(file_content)
            else:
                print(f"Error retrieving file for Node ID {node_id}")
        return files_content

    def validate_data(self, data):
        # Check if 'nodeTemplates' and 'relationshipTemplates' exist
        if "nodeTemplates" not in data or "relationshipTemplates" not in data:
            return (
                False,
                "Data must contain 'nodeTemplates' and 'relationshipTemplates'.",
            )

        # Check if 'nodeTemplates' and 'relationshipTemplates' are empty
        if not data["nodeTemplates"] and not data["relationshipTemplates"]:
            return False, "The topology is empty."

        # Check if 'nodeTemplates' has at least two elements
        if len(data.get("nodeTemplates", [])) < 2:
            return False, "'nodeTemplates' must have at least two elements."

        # Check if 'relationshipTemplates' has at least one element
        if len(data.get("relationshipTemplates", [])) < 1:
            return False, "'relationshipTemplates' must have at least one element."

        # Check if there are nodes with the prefix "Concrete Solution Of"
        if not any(
            node.get("name", "").startswith("Concrete Solution of")
            for node in data.get("nodeTemplates", [])
        ):
            return False, "Please generate a Solution Language!"

        # If all validations are successful
        return True, "Data is valid."

    def validate_path(self, nodes, relationships):
        # First, we filter the nodes that begin with "Concrete Solution of"
        concrete_solution_nodes = {
            node["id"]: node
            for node in nodes
            if node.get("name", "").startswith("Concrete Solution of")
        }

        # Then we filter the relationships that exist only between these nodes and whose name is "Aggregation" ist
        valid_relationships = [
            r
            for r in relationships
            if r.get("name") == "Aggregation"
            and r["sourceElement"]["ref"] in concrete_solution_nodes
            and r["targetElement"]["ref"] in concrete_solution_nodes
        ]

        # Checking the number of qubits for each valid relationship
        for relationship in valid_relationships:
            source_node = concrete_solution_nodes[relationship["sourceElement"]["ref"]]
            target_node = concrete_solution_nodes[relationship["targetElement"]["ref"]]

            # Access to the number of qubits
            source_qubits = (
                source_node["properties"].get("kvproperties", {}).get("QubitCount")
            )
            target_qubits = (
                target_node["properties"].get("kvproperties", {}).get("QubitCount")
            )

            # Check if the qubit numbers are equal
            if source_qubits != target_qubits:
                return (
                    False,
                    "Non-matching qubit counts in an aggregation relationship.",
                )

        # If all validations are successful
        return True, "Paths and qubit counts are valid."

    def fetch_file_content(self, concrete_solution_id):
        url = f"http://qc-atlas-api:6626/atlas/patterns/patternId/concrete-solutions/{concrete_solution_id}/file/content"
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return None

    def create_solution_path(self, nodes, relationships):
        # Filter the nodes that begin with "Concrete Solution of"
        solution_nodes = {
            node["id"]: node
            for node in nodes
            if node.get("name", "").startswith("Concrete Solution of")
        }

        # Filtering relationships of type 'Aggregation'
        aggregation_relationships = [
            r for r in relationships if r.get("name") == "Aggregation"
        ]

        # Check whether an aggregation relationship exists between the relevant nodes
        valid_solution_nodes = {}
        for relation in aggregation_relationships:
            source_id = relation["sourceElement"]["ref"]
            target_id = relation["targetElement"]["ref"]
            if source_id in solution_nodes and target_id in solution_nodes:
                valid_solution_nodes[source_id] = solution_nodes[source_id]
                valid_solution_nodes[target_id] = solution_nodes[target_id]

        # Delete unconnected nodes
        solution_nodes = valid_solution_nodes

        # Filtering the relationships that only exist between the valid nodes
        solution_relationships = [
            r
            for r in relationships
            if r["sourceElement"]["ref"] in solution_nodes
            and r["targetElement"]["ref"] in solution_nodes
        ]

        # Output of solution nodes and relationships for debugging purposes
        print("Solution Nodes:")
        for node_id, node in solution_nodes.items():
            print(f"Node ID: {node_id}, Node Data: {node}")

        print("\nSolution Relationships:")
        for relationship in solution_relationships:
            print(relationship)

        return solution_nodes, solution_relationships

    def aggregate_concrete_solution_files(
        self, concrete_solution_files, solution_nodes, solution_relationships
    ):
        # Here the contents of the file are created based on the data
        start_pattern_name = solution_nodes[list(solution_nodes.keys())[0]][
            "name"
        ].replace("Concrete Solution of ", "")
        reg_size = (
            solution_nodes[list(solution_nodes.keys())[0]]["properties"]
            .get("kvproperties", {})
            .get("QubitCount")
        )

        has_header = (
            solution_nodes[list(solution_nodes.keys())[0]]["properties"]
            .get("kvproperties", {})
            .get("hasHeader")
        )

        file_content = "// -- Start HEADER --\n"

        if has_header == "true":
            file_content += (
                f'// -- HEADER created from Pattern "{start_pattern_name}" --\n'
            )
            file_content += self.extract_header_until_reg(concrete_solution_files[0])
        else:
            file_content += "// -- No header defined --\n"

        file_content += "\n// -- End HEADER --\n\n"

        file_content += f"// -- Detected QREG size == {reg_size} --\n"
        file_content += f"// -- Detected CREG size == {reg_size} --\n"
        file_content += f"qreg q[{reg_size}];\n"
        file_content += f"creg meas[{reg_size}];\n"

        file_content += "\n"
        for node in solution_nodes.values():
            node_name = node["name"].replace("Concrete Solution of ", "")
            file_content += f'// -- Start CS from Pattern "{node_name}" --\n'
            file_content += self.extract_cs(concrete_solution_files.pop(0))
            file_content += f'\n// -- End CS from Pattern "{node_name}" --\n\n'

        for i in range(int(reg_size)):
            file_content += f"measure q[{i}] -> meas[{i}];\n"

        return file_content

    def extract_header_until_reg(self, text):
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("qreg ") or line.startswith("creg "):
                return "\n".join(lines[:i])
        return None
