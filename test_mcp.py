import json
from pathlib import Path
import ast
import base64
from tempfile import TemporaryDirectory
import unittest

from server import mcp
from tools.knowledge_base import KnowledgeIndex
from tools.run_assessment import (
    AssessmentIntakeForm,
    _load_instructions,
    _request_from_form,
    register as register_assessment,
)
from scripts.run_assessment import _load_request


class _TestMcp:
    """Capture registered handlers without needing an MCP transport."""

    def __init__(self) -> None:
        self.handlers = {}

    def tool(self):
        return self._register

    def resource(self, *_args, **_kwargs):
        return self._register

    def prompt(self):
        return self._register

    def _register(self, handler):
        self.handlers[handler.__name__] = handler
        return handler


class McpSurfaceTests(unittest.TestCase):
    def _prepare_assessment(self, operating_system: str) -> dict:
        test_mcp = _TestMcp()
        register_assessment(test_mcp)
        request = {
            "Sex": "F",
            "camera": "OPTOS",
            "DOB": "1990/04/20",
            "DiabetesStatus": "No",
            "SmokingStatus": "No",
            "image_paths": ["/client/right.jpg", "/client/left.jpg"],
        }
        return json.loads(
            test_mcp.handlers["prepare_assessment"](
                operating_system, "workstation1", json.dumps(request)
            )
        )

    def _assessment_handlers(self) -> dict:
        test_mcp = _TestMcp()
        register_assessment(test_mcp)
        return test_mcp.handlers

    def test_registers_tools_resources_and_prompts(self) -> None:
        tools = {item.name for item in mcp._tool_manager.list_tools()}
        resources = {str(item.uri) for item in mcp._resource_manager.list_resources()}
        templates = {
            item.uri_template for item in mcp._resource_manager.list_templates()
        }
        prompts = {item.name for item in mcp._prompt_manager.list_prompts()}

        self.assertIn("search_knowledge", tools)
        self.assertIn("start_retinal_assessment", tools)
        self.assertIn("list_assessment_endpoints", tools)
        self.assertIn("get_assessment_intake_schema", tools)
        self.assertIn("collect_assessment_intake", tools)
        self.assertIn("prepare_assessment", tools)
        self.assertIn("toku://knowledge/catalog", resources)
        self.assertIn("toku://assessment/guide", resources)
        self.assertIn("toku://knowledge/{document}", templates)
        self.assertIn("answer_from_knowledge", prompts)
        self.assertIn("run_assessment", prompts)

    def test_knowledge_index_refreshes_after_file_changes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "models.md"
            document.write_text("# Models\nRetina alpha model", encoding="utf-8")
            index = KnowledgeIndex(root)

            first = index.search("alpha")
            self.assertEqual(first[0][1].document.path, "models.md")

            document.write_text("# Models\nRetina beta model updated", encoding="utf-8")
            second = index.search("beta")
            self.assertEqual(second[0][1].document.path, "models.md")
            self.assertEqual(index.search("alpha"), [])

    def test_catalog_contains_readable_document_uris(self) -> None:
        index = KnowledgeIndex()
        catalog = json.loads(index.catalog())
        self.assertGreater(len(catalog["documents"]), 0)
        self.assertTrue(
            all(
                item["uri"].startswith("toku://knowledge/")
                for item in catalog["documents"]
            )
        )

    def test_assessment_guide_requires_structured_health_and_camera_choices(self) -> None:
        guide = _load_instructions()

        self.assertIn("| `DiabetesStatus` | `Yes`, `No` | None |", guide)
        self.assertIn("| `SmokingStatus` | `Yes`, `No` | None |", guide)
        self.assertIn("| `camera` | `NW400`, `NW500`, `OPTOS`, `Other` |", guide)
        self.assertIn(
            "Do not ask free-text questions for diabetes or smoking status.", guide
        )

    def test_assessment_intake_schema_provides_exact_ui_options(self) -> None:
        schema = json.loads(self._assessment_handlers()["get_assessment_intake_schema"]())
        fields = {field["name"]: field for field in schema["fields"]}

        self.assertEqual(
            fields["Sex"]["options"],
            [{"label": "Male", "value": "M"}, {"label": "Female", "value": "F"}],
        )
        self.assertEqual(
            [option["value"] for option in fields["camera"]["options"]],
            ["NW400", "NW500", "OPTOS", "Other"],
        )
        self.assertEqual(
            [option["value"] for option in fields["DiabetesStatus"]["options"]],
            ["Yes", "No"],
        )
        self.assertEqual(
            [option["value"] for option in fields["SmokingStatus"]["options"]],
            ["Yes", "No"],
        )
        self.assertEqual(fields["DOB"]["format"], "YYYY/MM/DD")

    def test_assessment_prompt_defaults_to_next_missing_field(self) -> None:
        prompt = self._assessment_handlers()["run_assessment"]("windows")

        self.assertIn("asking one next missing field at a time", prompt)
        self.assertIn("call collect_assessment_intake", prompt)
        self.assertIn("Never ask for the patient's first or last name", prompt)
        self.assertNotIn("Required intake UI schema", prompt)

    def test_assessment_start_tool_prevents_unneeded_conversion(self) -> None:
        response = json.loads(self._assessment_handlers()["start_retinal_assessment"]())

        self.assertEqual(response["missing_field_order"][0], "endpoint_name")
        self.assertEqual(response["next_question"]["text"], "Select the assessment endpoint.")
        self.assertEqual(
            response["next_question"]["options"], ["ai-cluster", "workstation1"]
        )
        self.assertIn("Do not narrate", response["next_action"])
        self.assertIn("Do not ask for image paths", response["image_rule"])
        self.assertIn("Do not call standalone_image_to_base64", response["conversion_rule"])

    def test_preparation_normalizes_safe_user_facing_values(self) -> None:
        handlers = self._assessment_handlers()
        request = {
            "Sex": "Male",
            "camera": "nw400",
            "DOB": "1985-06-02",
            "DiabetesStatus": "No",
            "SmokingStatus": "Never smoked",
            "image_paths": ["C:/right.jpg", "C:/left.jpg"],
        }

        package = json.loads(
            handlers["prepare_assessment"](
                "windows", "workstation1", json.dumps(request)
            )
        )
        prepared_request = json.loads(
            next(
                item["content"]
                for item in package["files"]
                if item["name"] == "assessment-request.json"
            )
        )

        self.assertEqual(prepared_request["Sex"], "M")
        self.assertEqual(prepared_request["camera"], "NW400")
        self.assertEqual(prepared_request["DOB"], "1985/06/02")
        self.assertEqual(prepared_request["SmokingStatus"], "No")
        self.assertEqual(len(package["normalizations"]), 4)
        self.assertTrue(prepared_request["FirstName"].startswith("Patient-"))
        self.assertTrue(prepared_request["LastName"].startswith("Auto-"))

    def test_interactive_form_uses_automatic_image_discovery(self) -> None:
        form = AssessmentIntakeForm(
            endpoint_name="workstation1",
            Sex="F",
            camera="Other",
            camera_other="Custom Camera 2000",
            DOB="1990/04/20",
            DiabetesStatus="No",
            SmokingStatus="Yes",
        )

        request = _request_from_form(form)

        self.assertEqual(request["endpoint_name"], "workstation1")
        self.assertEqual(request["camera"], "Custom Camera 2000")
        self.assertEqual(request["image_paths"], [])

    def test_windows_assessment_package_uses_powershell(self) -> None:
        package = self._prepare_assessment("windows")
        runner = next(
            item["content"]
            for item in package["files"]
            if item["name"] == "run_assessment.ps1"
        )

        self.assertEqual(package["operating_system"], "windows")
        self.assertEqual(
            package["client_requirements"],
            ["PowerShell 5.1 or newer", "No third-party PowerShell modules"],
        )
        self.assertEqual(
            [item["name"] for item in package["files"]],
            ["run_assessment.ps1", "assessment-request.json"],
        )
        self.assertIn(".\\run_assessment.ps1", package["command"])
        self.assertIn("Sex must be M or F.", runner)
        self.assertIn("DiabetesStatus must be Yes or No.", runner)
        self.assertIn("SmokingStatus must be Yes or No.", runner)
        self.assertIn("PowerShell 5.1 or newer is required.", runner)
        self.assertIn("Required built-in PowerShell command is unavailable", runner)
        self.assertIn("IsNullOrWhiteSpace([string]$_)", runner)

    def test_linux_and_macos_assessment_packages_use_posix_launcher(self) -> None:
        for operating_system in ("linux", "macos"):
            with self.subTest(operating_system=operating_system):
                package = self._prepare_assessment(operating_system)
                launcher = next(
                    item["content"]
                    for item in package["files"]
                    if item["name"] == "run_assessment.sh"
                )

                self.assertEqual(package["operating_system"], operating_system)
                self.assertEqual(
                    package["client_requirements"],
                    [
                        "Bash",
                        "Python 3.10 or newer",
                        "No third-party Python packages",
                    ],
                )
                self.assertEqual(
                    [item["name"] for item in package["files"]],
                    [
                        "run_assessment.sh",
                        "run_assessment.py",
                        "assessment-request.json",
                    ],
                )
                self.assertIn("chmod +x ./run_assessment.sh", package["command"])
                self.assertIn("Python 3.10 or newer is required.", launcher)
                self.assertIn("No third-party Python packages are needed.", launcher)

    def test_client_runner_validates_request_before_api_call(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image_paths = [root / "right.jpg", root / "left.jpg"]
            for image_path in image_paths:
                image_path.write_bytes(b"\xff\xd8\xfftest-image")

            request = {
                "EndpointUrl": "https://model.example/assessment",
                "FirstName": "Test",
                "LastName": "Patient",
                "Sex": "M",
                "camera": "NW500",
                "DOB": "1990/04/20",
                "DiabetesStatus": "Yes",
                "SmokingStatus": "No",
                "image_paths": [str(path) for path in image_paths],
            }
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")

            endpoint, payload = _load_request(request_path)
            self.assertEqual(endpoint, request["EndpointUrl"])
            self.assertEqual(len(payload["batchimages"]), 2)

            request["SmokingStatus"] = "Unknown"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SmokingStatus must be Yes or No"):
                _load_request(request_path)

    def test_client_runner_discovers_images_when_paths_are_omitted(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "right.jpg").write_bytes(b"\xff\xd8\xffright")
            (root / "left.png").write_bytes(b"\x89PNG\r\n\x1a\nleft")
            request = {
                "EndpointUrl": "https://model.example/assessment",
                "FirstName": "Test",
                "LastName": "Patient",
                "Sex": "M",
                "camera": "NW500",
                "DOB": "1990/04/20",
                "DiabetesStatus": "Yes",
                "SmokingStatus": "No",
            }
            request_path = root / "assessment-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")

            _, payload = _load_request(request_path)

            self.assertEqual(
                [image["ImageName"] for image in payload["batchimages"]],
                ["left.png", "right.jpg"],
            )

    def test_client_runner_discovers_base64_image_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "right.jpg").write_bytes(b"\xff\xd8\xffright")
            (root / "left.base64").write_text(
                base64.b64encode(b"\x89PNG\r\n\x1a\nleft").decode("ascii"),
                encoding="ascii",
            )
            request = {
                "EndpointUrl": "https://model.example/assessment",
                "FirstName": "Test",
                "LastName": "Patient",
                "Sex": "M",
                "camera": "NW500",
                "DOB": "1990/04/20",
                "DiabetesStatus": "Yes",
                "SmokingStatus": "No",
            }
            request_path = root / "assessment-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")

            _, payload = _load_request(request_path)

            self.assertEqual(len(payload["batchimages"]), 2)
            self.assertEqual(payload["batchimages"][0]["ImageName"], "left.base64")

    def test_posix_runner_uses_only_python_standard_library(self) -> None:
        runner_path = Path(__file__).parent / "scripts" / "run_assessment.py"
        module = ast.parse(runner_path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        self.assertEqual(
            imports,
            {
                "__future__",
                "argparse",
                "base64",
                "datetime",
                "json",
                "pathlib",
                "re",
                "sys",
                "urllib",
            },
        )


if __name__ == "__main__":
    unittest.main()
