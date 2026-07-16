"""Prepare assessment artifacts for execution on the MCP client's machine."""

import json
import logging
from pathlib import Path
import re
import secrets
from typing import Literal

from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

logger = logging.getLogger("Venus.run_assessment")

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
_INSTRUCTIONS_FILE = _KNOWLEDGE_DIR / "assessment-guide.md"
_ENDPOINTS_FILE = _KNOWLEDGE_DIR / "templates" / "endpoints.json"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_VALID_OS_NAMES = {"windows", "linux", "macos"}
_VALID_SEX = {"M", "F"}
_VALID_YES_NO = {"Yes", "No"}
_INTAKE_SCHEMA = {
    "fields": [
        {
            "name": "Sex",
            "required": True,
            "input": "single_select",
            "question": "What is the patient's sex?",
            "options": [
                {"label": "Male", "value": "M"},
                {"label": "Female", "value": "F"},
            ],
        },
        {
            "name": "camera",
            "required": True,
            "input": "single_select_with_other",
            "question": "What camera was used to capture the images?",
            "options": [
                {"label": "NW400", "value": "NW400"},
                {"label": "NW500", "value": "NW500"},
                {"label": "OPTOS", "value": "OPTOS"},
                {"label": "Other", "value": "Other"},
            ],
            "other_question": "Enter the camera model.",
        },
        {
            "name": "DOB",
            "required": True,
            "input": "date",
            "question": "What is the patient's date of birth?",
            "format": "YYYY/MM/DD",
            "example": "1985/06/02",
        },
        {
            "name": "DiabetesStatus",
            "required": True,
            "input": "single_select",
            "question": "Does the patient have diabetes?",
            "options": [{"label": "Yes", "value": "Yes"}, {"label": "No", "value": "No"}],
        },
        {
            "name": "SmokingStatus",
            "required": True,
            "input": "single_select",
            "question": "Is the patient a smoker?",
            "options": [{"label": "Yes", "value": "Yes"}, {"label": "No", "value": "No"}],
        },
    ]
}


class AssessmentIntakeForm(BaseModel):
    """Native MCP elicitation schema for a complete assessment request."""

    endpoint_name: str = Field(
        description="Choose one exact endpoint name: ai-cluster or workstation1."
    )
    Sex: Literal["M", "F"] = Field(description="Select M for Male or F for Female.")
    camera: Literal["NW400", "NW500", "OPTOS", "Other"] = Field(
        description="Select the image capture camera."
    )
    camera_other: str = Field(
        default="",
        description="Camera model only when camera is Other; otherwise leave blank.",
    )
    DOB: str = Field(
        pattern=r"^\d{4}/\d{2}/\d{2}$",
        description="Date of birth in YYYY/MM/DD format, for example 1985/06/02.",
    )
    DiabetesStatus: Literal["Yes", "No"] = Field(
        description="Select whether the patient has diabetes."
    )
    SmokingStatus: Literal["Yes", "No"] = Field(
        description="Select whether the patient is a smoker."
    )


def _load_instructions() -> str:
    """Load the assessment workflow instructions from disk."""
    return _INSTRUCTIONS_FILE.read_text(encoding="utf-8")


def _load_endpoints() -> dict[str, dict]:
    return json.loads(_ENDPOINTS_FILE.read_text(encoding="utf-8"))


def _endpoint_choices() -> list[dict[str, object]]:
    """Return only literal endpoint names suitable for user selection."""
    return [{"endpoint_name": name} for name in sorted(_load_endpoints())]


def _random_identity_value(prefix: str) -> str:
    """Generate a random placeholder identity string; never derived from user input."""
    return f"{prefix}-{secrets.token_hex(4)}"


def _fill_identity_defaults(request: dict) -> None:
    """Auto-fill FirstName/LastName with random strings when not supplied.

    FirstName and LastName are no longer collected from the user; the model
    wrapper API call always receives random placeholder values instead.
    """
    if not str(request.get("FirstName", "")).strip():
        request["FirstName"] = _random_identity_value("Patient")
    if not str(request.get("LastName", "")).strip():
        request["LastName"] = _random_identity_value("Auto")


def _normalize_request(request: dict) -> list[dict[str, str]]:
    """Normalize unambiguous user-facing values to the model wrapper contract."""
    normalizations: list[dict[str, str]] = []

    def normalize(field: str, replacements: dict[str, str]) -> None:
        value = request.get(field)
        if not isinstance(value, str):
            return
        replacement = replacements.get(value.strip().lower())
        if replacement and replacement != value:
            request[field] = replacement
            normalizations.append({"field": field, "from": value, "to": replacement})

    normalize("Sex", {"m": "M", "male": "M", "f": "F", "female": "F"})
    normalize(
        "DiabetesStatus",
        {"yes": "Yes", "y": "Yes", "true": "Yes", "no": "No", "n": "No", "false": "No"},
    )
    normalize(
        "SmokingStatus",
        {
            "yes": "Yes",
            "y": "Yes",
            "true": "Yes",
            "no": "No",
            "n": "No",
            "false": "No",
            "never": "No",
            "never smoked": "No",
            "non-smoker": "No",
            "nonsmoker": "No",
        },
    )
    normalize("camera", {"nw400": "NW400", "nw500": "NW500", "optos": "OPTOS"})

    dob = request.get("DOB")
    if isinstance(dob, str) and re.fullmatch(r"\d{4}[-.]\d{2}[-.]\d{2}", dob.strip()):
        normalized_dob = re.sub(r"[-.]", "/", dob.strip())
        request["DOB"] = normalized_dob
        normalizations.append({"field": "DOB", "from": dob, "to": normalized_dob})

    return normalizations


def _validate_request(request: dict) -> None:
    required_strings = (
        "FirstName",
        "LastName",
        "Sex",
        "camera",
        "DOB",
        "DiabetesStatus",
        "SmokingStatus",
    )
    # FirstName/LastName are no longer user-supplied; _fill_identity_defaults
    # must run before this validation so they are always present here.
    missing = [key for key in required_strings if not request.get(key)]
    if missing:
        raise ValueError(f"Missing required assessment fields: {', '.join(missing)}")
    if request["Sex"] not in _VALID_SEX:
        raise ValueError("Sex must be M or F")
    if request["DiabetesStatus"] not in _VALID_YES_NO:
        raise ValueError("DiabetesStatus must be Yes or No")
    if request["SmokingStatus"] not in _VALID_YES_NO:
        raise ValueError("SmokingStatus must be Yes or No")
    if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", request["DOB"]):
        raise ValueError("DOB must match YYYY/MM/DD")
    image_paths = request.get("image_paths", [])
    if not isinstance(image_paths, list):
        raise ValueError("image_paths must be an array when supplied")
    if not all(isinstance(path, str) and path.strip() for path in image_paths):
        raise ValueError("Every image path must be a non-empty string")


def _request_from_form(form: AssessmentIntakeForm) -> dict:
    """Convert native form data into the request accepted by prepare_assessment."""
    request = form.model_dump()
    camera_other = request.pop("camera_other", "").strip()
    if request["camera"] == "Other":
        if not camera_other:
            raise ValueError("camera_other is required when camera is Other")
        request["camera"] = camera_other
    request["image_paths"] = []
    return request


def register(mcp) -> None:
    @mcp.resource("toku://assessment/guide", mime_type="text/markdown")
    def assessment_guide() -> str:
        """Read the client-side TokuEyes assessment workflow."""
        return _load_instructions()

    @mcp.resource("toku://assessment/endpoints", mime_type="application/json")
    def assessment_endpoints() -> str:
        """List the model wrapper endpoints available to assessment clients."""
        return json.dumps(_load_endpoints(), indent=2)

    @mcp.tool()
    def start_retinal_assessment() -> str:
        """Start a retinal assessment. Use this for 'run assessment' requests.

        This is the assessment entry point. Call it before any conversion tool.
        Call collect_assessment_intake next to attempt the native MCP elicitation
        form. Only if that returns status elicitation_unavailable should you fall
        back to asking one next missing patient field at a time in chat, using
        next_question below.
        """
        return json.dumps(
            {
                "next_action": "Call collect_assessment_intake now. Only if it returns status elicitation_unavailable, ask the exact next_question one field at a time. Do not narrate tool use, create todos, or call list_assessment_endpoints.",
                "next_question": {
                    "field": "endpoint_name",
                    "text": "Select the assessment endpoint.",
                    "options": [item["endpoint_name"] for item in _endpoint_choices()],
                },
                "missing_field_order": [
                    "endpoint_name",
                    "Sex",
                    "camera",
                    "DOB",
                    "DiabetesStatus",
                    "SmokingStatus",
                ],
                "identity_rule": "Do not ask for the patient's first or last name. FirstName and LastName are auto-generated random placeholders for the model wrapper API call.",
                "endpoint_rule": "Use next_question.options exactly. Do not describe or invent endpoint labels.",
                "image_rule": "Do not ask for image paths or image/Base64 format. prepare_assessment discovers supported files beside assessment-request.json.",
                "conversion_rule": "Do not call standalone_image_to_base64 or standalone_base64_to_image for an assessment unless the runner reports that it cannot use a specific file.",
            },
            separators=(",", ":"),
        )

    @mcp.tool()
    def list_assessment_endpoints() -> str:
        """List literal configured assessment endpoint names for direct selection.

        Present only returned endpoint_name values to the user. Do not include
        endpoint URLs, requirements, or descriptions. Do not invent
        labels such as model names, workflows, Retinal screening, CLAIR, or
        BioAge: those are assessment intents, not configured endpoints.
        Pass the selected endpoint_name unchanged to prepare_assessment.
        """
        return json.dumps({"endpoints": _endpoint_choices()}, indent=2)

    @mcp.tool()
    def get_assessment_intake_schema() -> str:
        """Return exact UI fields, options, values, and formats for the chat-fallback intake.

        Only call this after collect_assessment_intake returns status
        elicitation_unavailable. Render each single_select field as options
        using its label and submit its value. Do not replace these controls
        with free-text questions. The DOB question must visibly state
        YYYY/MM/DD and use its example. Only camera Other permits a
        follow-up text field.
        """
        return json.dumps(_INTAKE_SCHEMA, indent=2)

    @mcp.tool()
    async def collect_assessment_intake(ctx: Context) -> str:
        """Open the native MCP elicitation form to collect assessment intake.

        Call this immediately after start_retinal_assessment. It attempts a
        single structured form via ctx.elicit; the MCP SDK negotiates whether
        the connected client actually supports elicitation, so do not guess
        client capability yourself. Only fall back to asking one field at a
        time in normal chat if this returns status elicitation_unavailable.
        """
        try:
            result = await ctx.elicit(
                "Complete the assessment intake. Do not include patient name: it is auto-generated. All other values are required. The runner will automatically find image files in its working directory.",
                AssessmentIntakeForm,
            )
        except Exception as error:
            logger.warning("collect_assessment_intake: client rejected elicitation: %s: %s", type(error).__name__, error)
            return json.dumps(
                {
                    "status": "elicitation_unavailable",
                    "reason": f"{type(error).__name__}: {error}",
                    "next_action": "Ask only the next missing field in normal chat. Do not call another intake tool.",
                },
            )

        if result.action != "accept" or result.data is None:
            return json.dumps(
                {
                    "status": result.action,
                    "message": "The assessment intake was not submitted. Do not prepare or run an assessment.",
                },
                indent=2,
            )

        request = _request_from_form(result.data)
        _fill_identity_defaults(request)
        normalizations = _normalize_request(request)
        _validate_request(request)
        return json.dumps(
            {
                "status": "accepted",
                "endpoint_name": request.pop("endpoint_name"),
                "request": request,
                "normalizations": normalizations,
                "next_action": "Call prepare_assessment with this endpoint_name and request serialized as JSON.",
            },
            indent=2,
        )

    @mcp.prompt()
    def run_assessment(operating_system: str = "", request_details: str = "") -> str:
        """Start a minimal client-side retinal assessment workflow."""
        return (
            "Run a client-side assessment. Collect only missing patient metadata. Never "
            "ask for the patient's first or last name: those are auto-generated random "
            "placeholders. "
            "Call start_retinal_assessment first, then immediately call collect_assessment_intake "
            "to attempt the native MCP elicitation form. Only if that returns status "
            "elicitation_unavailable, fall back to asking one next missing field at a time in "
            "chat, using start_retinal_assessment's next_question. "
            "Do not ask for image paths or image/Base64 format: the client runner discovers files beside assessment-request.json. "
            "Do not call list_assessment_endpoints after start_retinal_assessment. "
            "Known operating system: "
            + (operating_system or "not provided; detect it or ask the user")
            + ". Known request details: "
            + (request_details or "None supplied yet.")
        )

    @mcp.tool()
    def prepare_assessment(
        operating_system: str,
        endpoint_name: str,
        request_json: str,
    ) -> str:
        """Prepare fixed client-side assessment files and an exact run command.

        This tool never reads client images and never calls the model API. Pass
        request_json with patient fields and optionally image_paths. Do not
        include FirstName or LastName: they are auto-generated random placeholder
        strings for the model wrapper API call. If image_paths is omitted, the
        client runner discovers supported image and Base64 files beside the
        request file. Supported operating systems are windows, linux, and macos.
        """
        os_name = operating_system.strip().lower()
        if os_name not in _VALID_OS_NAMES:
            raise ValueError("operating_system must be windows, linux, or macos")

        endpoints = _load_endpoints()
        if endpoint_name not in endpoints:
            raise ValueError(
                f"Unknown endpoint_name '{endpoint_name}'. Available: "
                + ", ".join(sorted(endpoints))
            )
        endpoint_url = endpoints[endpoint_name].get("model_wrapper_endpoint", "")
        if not re.match(r"^https?://", endpoint_url):
            raise ValueError(f"Endpoint '{endpoint_name}' has an invalid URL")

        request = json.loads(request_json)
        if not isinstance(request, dict):
            raise ValueError("request_json must contain a JSON object")
        _fill_identity_defaults(request)
        normalizations = _normalize_request(request)
        _validate_request(request)
        request["EndpointUrl"] = endpoint_url

        if os_name == "windows":
            files = [
                {
                    "name": "run_assessment.ps1",
                    "content": (_SCRIPTS_DIR / "run_assessment.ps1").read_text(
                        encoding="utf-8"
                    ),
                }
            ]
            command = (
                "& .\\run_assessment.ps1 -RequestFile "
                "'.\\assessment-request.json' -OutputDir '.\\results'"
            )
        else:
            files = [
                {
                    "name": "run_assessment.sh",
                    "content": (_SCRIPTS_DIR / "run_assessment.sh").read_text(
                        encoding="utf-8"
                    ),
                },
                {
                    "name": "run_assessment.py",
                    "content": (_SCRIPTS_DIR / "run_assessment.py").read_text(
                        encoding="utf-8"
                    ),
                },
            ]
            command = (
                "chmod +x ./run_assessment.sh && ./run_assessment.sh --request-file "
                "./assessment-request.json --output-dir ./results"
            )

        files.append(
            {
                "name": "assessment-request.json",
                "content": json.dumps(request, indent=2),
            }
        )

        return json.dumps(
            {
                "execution_location": "MCP client machine only",
                "server_called_model_api": False,
                "operating_system": os_name,
                "normalizations": normalizations,
                "client_requirements": (
                    [
                        "PowerShell 5.1 or newer",
                        "No third-party PowerShell modules",
                    ]
                    if os_name == "windows"
                    else [
                        "Bash",
                        "Python 3.10 or newer",
                        "No third-party Python packages",
                    ]
                ),
                "files": files,
                "command": command,
                "next_steps": [
                    "Write both returned files into one client-local working directory.",
                    "Run the command exactly in that directory.",
                    "Read the response_path printed by the runner and summarize the JSON result.",
                ],
            },
            indent=2,
        )
