"""Module containing the BloQCat Framework endpoint(s) of the v1 API."""

from flask import jsonify, request
from typing import Dict
from flask.helpers import url_for
from flask.views import MethodView
from dataclasses import dataclass
from http import HTTPStatus
from flask import Response

from .root import API_V1
from .models import TopologyViewSchema
from ..jwt import DemoUser

import xml.etree.ElementTree as ET
import requests
import re


@API_V1.route("/bloqcat/winery/topology/deploy/json", methods=["POST"])
class TopologyView(MethodView):
    """POST endpoint to retrieve the aggregated solution."""

    def post(self):
        # Parse the JSON topology file from the request body
        try:
            data = request.json
        except ET.ParseError as e:
            return f"Invalid JSON data: {str(e)}", HTTPStatus.BAD_REQUEST

        # Validierung der Daten
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
            return "Fehler beim Abrufen der Dateien.", HTTPStatus.BAD_REQUEST

        # Aggregieren der Dateien
        file_content = self.aggregate_concrete_solution_files(
            concrete_solution_files, solution_nodes, solution_relationships
        )

        # Erstellen des Dateiinhalts (nach erfolgreicher Validierung)
        # file_content = self.create_file_content(data)

        # Erstellen einer Response mit dem Dateiinhalt
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
                # Hier drucken wir den Inhalt jeder Datei aus
                print(f"Inhalt der Datei für Node ID {node_id}:")
                print(file_content)
            else:
                print(f"Fehler beim Abrufen der Datei für Node ID {node_id}")
        return files_content

    def validate_data(self, data):
        # Überprüfen, ob 'nodeTemplates' und 'relationshipTemplates' vorhanden sind
        if "nodeTemplates" not in data or "relationshipTemplates" not in data:
            return (
                False,
                "Daten müssen 'nodeTemplates' und 'relationshipTemplates' enthalten.",
            )

        # Überprüfen, ob 'nodeTemplates' und 'relationshipTemplates' leer sind
        if not data["nodeTemplates"] and not data["relationshipTemplates"]:
            return False, "Die Topologie ist leer."

        # Überprüfen, ob 'nodeTemplates' mindestens zwei Elemente hat
        if len(data.get("nodeTemplates", [])) < 2:
            return False, "'nodeTemplates' muss mindestens zwei Elemente haben."

        # Überprüfen, ob 'relationshipTemplates' mindestens ein Element hat
        if len(data.get("relationshipTemplates", [])) < 1:
            return False, "'relationshipTemplates' muss mindestens ein Element haben."

        # Überprüfen, ob es Knoten mit dem Präfix "Concrete Solution Of" gibt
        if not any(
            node.get("name", "").startswith("Concrete Solution of")
            for node in data.get("nodeTemplates", [])
        ):
            return False, "Bitte generieren Sie eine Solution Language!"

        # Wenn alle Validierungen erfolgreich sind
        return True, "Daten sind gültig."

    def validate_path(self, nodes, relationships):
        # Zuerst filtern wir die Nodes, die mit "Concrete Solution of" beginnen
        concrete_solution_nodes = {
            node["id"]: node
            for node in nodes
            if node.get("name", "").startswith("Concrete Solution of")
        }

        # Dann filtern wir die Relationships, die nur zwischen diesen Nodes existieren und deren Name "Aggregation" ist
        valid_relationships = [
            r
            for r in relationships
            if r.get("name") == "Aggregation"
            and r["sourceElement"]["ref"] in concrete_solution_nodes
            and r["targetElement"]["ref"] in concrete_solution_nodes
        ]

        # Überprüfen der Qubit-Anzahl für jede valide Beziehung
        for relationship in valid_relationships:
            source_node = concrete_solution_nodes[relationship["sourceElement"]["ref"]]
            target_node = concrete_solution_nodes[relationship["targetElement"]["ref"]]

            # Zugriff auf die Qubit-Anzahl
            source_qubits = (
                source_node["properties"].get("kvproperties", {}).get("QubitCount")
            )
            target_qubits = (
                target_node["properties"].get("kvproperties", {}).get("QubitCount")
            )

            # Überprüfen, ob die Qubit-Anzahlen gleich sind
            if source_qubits != target_qubits:
                return (
                    False,
                    "Nicht übereinstimmende Qubit-Anzahlen in einer Aggregations-Beziehung.",
                )

        # Wenn alle Validierungen erfolgreich sind
        return True, "Pfade und Qubit-Anzahlen sind gültig."

    def fetch_file_content(self, concrete_solution_id):
        url = f"http://qc-atlas-api:6626/atlas/patterns/patternId/concrete-solutions/{concrete_solution_id}/file/content"
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return None

    def create_solution_path(self, nodes, relationships):
        # Filtern der Knoten, die mit "Concrete Solution of" beginnen
        solution_nodes = {
            node["id"]: node
            for node in nodes
            if node.get("name", "").startswith("Concrete Solution of")
        }

        # Filtern der Relationships vom Typ 'Aggregation'
        aggregation_relationships = [
            r for r in relationships if r.get("name") == "Aggregation"
        ]

        # Überprüfen, ob eine Aggregationsbeziehung zwischen den relevanten Knoten besteht
        valid_solution_nodes = {}
        for relation in aggregation_relationships:
            source_id = relation["sourceElement"]["ref"]
            target_id = relation["targetElement"]["ref"]
            if source_id in solution_nodes and target_id in solution_nodes:
                valid_solution_nodes[source_id] = solution_nodes[source_id]
                valid_solution_nodes[target_id] = solution_nodes[target_id]

        # Löschen Sie nicht verbundene Knoten
        solution_nodes = valid_solution_nodes

        # Filtern der Relationships, die nur zwischen den gültigen Nodes existieren
        solution_relationships = [
            r
            for r in relationships
            if r["sourceElement"]["ref"] in solution_nodes
            and r["targetElement"]["ref"] in solution_nodes
        ]

        # Ausgabe der Lösungsknoten und -beziehungen für Debugging-Zwecke
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
        # Hier wird der Inhalt der Datei basierend auf den Daten erstellt
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

        file_content = f"// -- Start HEADER --\n"

        if has_header == "true":
            file_content += (
                f'// -- HEADER created from Pattern "{start_pattern_name}" --\n'
            )
            file_content += self.extract_header_until_reg(concrete_solution_files[0])
        else:
            file_content += "// -- No header defined --\n"

        file_content += f"\n// -- End HEADER --\n\n"

        file_content += f"// -- Detected QREG size == {reg_size} --\n"
        file_content += f"// -- Detected CREG size == {reg_size} --\n"
        file_content += f"qreg q[{reg_size}];\n"
        file_content += f"creg meas[{reg_size}];\n"

        file_content += f"\n"
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
