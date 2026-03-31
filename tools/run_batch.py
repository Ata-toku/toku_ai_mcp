"""MCP tool: run a batch AI assessment via the model wrapper API.

Multi-step flow:
  Step 0 (list_batch_endpoints)   — present endpoint options as buttons (default: ai-cluster).
  Step 1 (validate_batch_request) — validate patient metadata + image paths, return issues or OK.
  Step 2 (run_batch_assessment)   — build & return a client-side curl script that sends the request
                                    and validates the response against the success schema.
"""

import json
from pathlib import Path

# ── Endpoint loader (reads from knowledge/templates/endpoints.json) ──────────

_ENDPOINTS_FILE = Path(__file__).parent.parent / "knowledge" / "templates" / "endpoints.json"
_DEFAULT_ENDPOINT = "ai-cluster"


def _load_endpoints() -> dict:
    """Load endpoints from the JSON config file."""
    with open(_ENDPOINTS_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    # Normalise to {name: {url, name}} for internal use
    result = {}
    for key, ep in raw.items():
        result[key] = {
            "url": ep["model_wrapper_endpoint"],
            "name": ep.get("name", key),
            "requirements": ep.get("requirements", []),
        }
    return result

# ── Required request fields ──────────────────────────────────────────────────

_REQUIRED_FIELDS = {
    "FirstName":      {"type": "string", "description": "Patient first name"},
    "LastName":       {"type": "string", "description": "Patient last name"},
    "Sex":            {"type": "string", "description": "Patient sex (M or F)"},
    "camera":         {"type": "string", "description": "Camera type (e.g. OPTOS, TOPCON, CANON)"},
    "DOB":            {"type": "string", "description": "Date of birth (YYYY/MM/DD)"},
    "DiabetesStatus": {"type": "string", "description": "Diabetes status (Yes or No)"},
    "SmokingStatus":  {"type": "string", "description": "Smoking status (Yes or No)"},
}

# ── Response success schema top-level keys ───────────────────────────────────

_RESPONSE_EXPECTED_KEYS = [
    "FirstName", "LastName", "Sex", "camera", "DOB",
    "DiabetesStatus", "SmokingStatus", "batchimages",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_metadata(metadata: dict) -> list[str]:
    """Return list of missing/invalid field messages."""
    issues = []
    for field, info in _REQUIRED_FIELDS.items():
        val = metadata.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            issues.append(f"Missing required field: '{field}' — {info['description']}")
    # Specific validations
    sex = metadata.get("Sex", "")
    if sex and sex.upper() not in ("M", "F"):
        issues.append(f"Invalid 'Sex' value: '{sex}'. Must be 'M' or 'F'.")
    for yn_field in ("DiabetesStatus", "SmokingStatus"):
        val = metadata.get(yn_field, "")
        if val and val.capitalize() not in ("Yes", "No"):
            issues.append(f"Invalid '{yn_field}' value: '{val}'. Must be 'Yes' or 'No'.")
    dob = metadata.get("DOB", "")
    if dob:
        import re
        if not re.match(r"^\d{4}/\d{2}/\d{2}$", dob):
            issues.append(f"Invalid 'DOB' format: '{dob}'. Expected YYYY/MM/DD.")
    return issues


def _validate_images(image_paths: list[str]) -> list[str]:
    """Return list of image-related issues (checked server-side — path format only)."""
    issues = []
    if not image_paths:
        issues.append("No image paths provided. At least 2 retinal images are required.")
        return issues
    if len(image_paths) < 2:
        issues.append(f"Only {len(image_paths)} image(s) provided. At least 2 retinal images are required (one per eye).")
    for i, p in enumerate(image_paths):
        if not p or not p.strip():
            issues.append(f"Image path #{i+1} is empty.")
        elif not any(p.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif")):
            issues.append(f"Image path #{i+1} ('{p}') does not have a recognised image extension.")
    return issues


def _resolve_endpoint(endpoint_name: str) -> dict | None:
    """Resolve a named endpoint key to {url, name}. Raw URLs are NOT accepted."""
    endpoints = _load_endpoints()
    return endpoints.get(endpoint_name.lower().strip())


def _endpoint_options() -> list[dict]:
    """Return endpoint options formatted for vscode_askQuestions."""
    endpoints = _load_endpoints()
    options = []
    for key, ep in endpoints.items():
        req = ep["requirements"][0] if ep["requirements"] else ""
        options.append({
            "label": key,
            "description": req,
            "recommended": key == _DEFAULT_ENDPOINT,
        })
    # Ensure default comes first
    options.sort(key=lambda o: (0 if o["recommended"] else 1))
    return options


# ── Tool registration ────────────────────────────────────────────────────────

def register(mcp):

    @mcp.tool()
    def validate_batch_request(
        endpoint_name: str = "",
        image_paths: list[str] = None,
        FirstName: str = "",
        LastName: str = "",
        Sex: str = "",
        camera: str = "",
        DOB: str = "",
        DiabetesStatus: str = "",
        SmokingStatus: str = "",
    ) -> str:
        """Step 1: Validate a batch AI assessment request before sending.

        Checks patient metadata fields and image paths. Returns a list of
        issues that must be resolved, OR an 'ALL_VALID' status meaning
        you can proceed to run_batch_assessment with the same parameters.

        MANDATORY WORKFLOW — follow this exactly:
          0. ALWAYS call list_batch_endpoints FIRST. Never skip this step.
             Present the returned buttons to the user and wait for their selection.
          1. Gather patient info + image file paths from the user.
          2. Call this tool with the endpoint_name chosen by the user in step 0.
          3. If issues are returned, ask the user to fix them, then re-validate.
          4. When ALL_VALID, call run_batch_assessment with the same parameters.

        endpoint_name MUST be a short name key (e.g. 'ai-cluster', 'workstation1')
        exactly as returned by list_batch_endpoints. Do NOT pass a URL here — URLs
        are resolved internally. If endpoint_name is empty, this tool will return
        an ENDPOINT_REQUIRED error and instruct you to call list_batch_endpoints.
        Image paths are absolute paths on the CLIENT machine (e.g. C:/images/left.png).
        At least 2 images are required (typically one per eye).

        Args:
            endpoint_name: Short name key of the target endpoint (e.g. 'ai-cluster').
                           Must match a key from list_batch_endpoints. Never pass a URL.
            image_paths: List of absolute image file paths on the client machine.
            FirstName: Patient first name.
            LastName: Patient last name.
            Sex: Patient sex (M or F).
            camera: Camera type (OPTOS, TOPCON, CANON, etc.).
            DOB: Date of birth in YYYY/MM/DD format.
            DiabetesStatus: Diabetes status (Yes or No).
            SmokingStatus: Smoking status (Yes or No).
        """
        if image_paths is None:
            image_paths = []

        # 0. If no endpoint_name provided, force endpoint selection via buttons
        if not endpoint_name or not endpoint_name.strip():
            return json.dumps({
                "status": "ENDPOINT_REQUIRED",
                "instruction": (
                    "No endpoint was specified. "
                    "Call list_batch_endpoints first, then call vscode_askQuestions with "
                    "the returned options so the user can pick via buttons. "
                    "Then call validate_batch_request again with the chosen endpoint_name. "
                    "The recommended default is 'ai-cluster'."
                ),
                "question": {
                    "header": "Select AI Endpoint",
                    "question": "Which endpoint should be used for the batch AI assessment?",
                    "options": _endpoint_options(),
                    "allowFreeformInput": True,
                },
            }, indent=2)

        all_issues = []

        # 1. Endpoint — only named keys accepted, never raw URLs
        ep = _resolve_endpoint(endpoint_name)
        if ep is None:
            known = ", ".join(_load_endpoints().keys())
            all_issues.append(
                f"Unknown endpoint name: '{endpoint_name}'. "
                f"Must be one of: {known}. "
                f"Call list_batch_endpoints to see available options."
            )

        # 2. Metadata
        metadata = {
            "FirstName": FirstName, "LastName": LastName, "Sex": Sex,
            "camera": camera, "DOB": DOB,
            "DiabetesStatus": DiabetesStatus, "SmokingStatus": SmokingStatus,
        }
        all_issues.extend(_validate_metadata(metadata))

        # 3. Images
        all_issues.extend(_validate_images(image_paths))

        if all_issues:
            return json.dumps({
                "status": "INVALID",
                "issues": all_issues,
                "instruction": (
                    "Ask the user to provide the missing or corrected information, "
                    "then call validate_batch_request again with updated values."
                ),
            }, indent=2)

        return json.dumps({
            "status": "ALL_VALID",
            "endpoint_name": endpoint_name,
            "endpoint": ep,
            "patient": metadata,
            "image_count": len(image_paths),
            "instruction": (
                "Validation passed. Now call run_batch_assessment with the "
                "exact same parameters to get the executable script."
            ),
        }, indent=2)

    @mcp.tool()
    def run_batch_assessment(
        endpoint_name: str,
        image_paths: list[str],
        FirstName: str,
        LastName: str,
        Sex: str,
        camera: str,
        DOB: str,
        DiabetesStatus: str,
        SmokingStatus: str,
    ) -> str:
        """Step 2: Get a client-side script that sends a batch AI assessment and validates the response.

        ONLY call this AFTER validate_batch_request returned ALL_VALID.

        The returned script (PowerShell or bash):
          1. Reads each image file from disk and base64-encodes it.
          2. Builds the full JSON payload.
          3. Sends a POST request to the model wrapper endpoint.
          4. Validates the response has the expected schema fields.
          5. Saves the response to a JSON file.

        Args:
            endpoint_name: Short name key of the target endpoint (same as validated).
                           Must match a key from list_batch_endpoints. Never pass a URL.
            image_paths: List of absolute image file paths on the client machine.
            FirstName: Patient first name.
            LastName: Patient last name.
            Sex: Patient sex (M or F).
            camera: Camera type.
            DOB: Date of birth (YYYY/MM/DD).
            DiabetesStatus: Diabetes status (Yes or No).
            SmokingStatus: Smoking status (Yes or No).
        """
        # Re-validate (safety net)
        ep = _resolve_endpoint(endpoint_name)
        if ep is None:
            known = ", ".join(_load_endpoints().keys())
            return json.dumps({"error": f"Unknown endpoint name: '{endpoint_name}'. Must be one of: {known}. Run validate_batch_request first."})

        metadata = {
            "FirstName": FirstName, "LastName": LastName, "Sex": Sex,
            "camera": camera, "DOB": DOB,
            "DiabetesStatus": DiabetesStatus, "SmokingStatus": SmokingStatus,
        }
        meta_issues = _validate_metadata(metadata)
        img_issues = _validate_images(image_paths)
        if meta_issues or img_issues:
            return json.dumps({
                "error": "Validation failed. Call validate_batch_request first.",
                "issues": meta_issues + img_issues,
            }, indent=2)

        url = ep["url"]
        expected_keys_json = json.dumps(_RESPONSE_EXPECTED_KEYS)

        # Build PowerShell script
        ps_image_blocks = []
        for i, p in enumerate(image_paths):
            safe_p = p.replace("'", "''")
            img_name = p.replace("\\", "/").split("/")[-1]
            ps_image_blocks.append(
                f"  # Image {i+1}\n"
                f"  $imgPath{i} = '{safe_p}'\n"
                f"  if (-not (Test-Path $imgPath{i})) {{ Write-Error \"Image not found: $imgPath{i}\"; exit 1 }}\n"
                f"  $bytes{i} = [System.IO.File]::ReadAllBytes($imgPath{i})\n"
                f"  $b64_{i} = [System.Convert]::ToBase64String($bytes{i})\n"
                f"  $images += @{{ ImageName = '{img_name}'; Image64 = $b64_{i} }}"
            )

        ps_meta = json.dumps(metadata, indent=4)
        ps_script = f'''# ── Batch AI Assessment ──
# Endpoint: {url}
# Patient: {FirstName} {LastName}
# Images: {len(image_paths)}

$ErrorActionPreference = "Stop"
Write-Host "=== Step 1: Reading and encoding images ===" -ForegroundColor Cyan

$images = @()
{chr(10).join(ps_image_blocks)}

Write-Host "  Encoded $($images.Count) image(s) successfully." -ForegroundColor Green

Write-Host "=== Step 2: Building request payload ===" -ForegroundColor Cyan

$payload = @{{
    FirstName      = '{FirstName}'
    LastName       = '{LastName}'
    Sex            = '{Sex}'
    camera         = '{camera}'
    DOB            = '{DOB}'
    DiabetesStatus = '{DiabetesStatus}'
    SmokingStatus  = '{SmokingStatus}'
    batchimages    = $images
}}

$jsonBody = $payload | ConvertTo-Json -Depth 5 -Compress
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)
$sizeMB = [math]::Round($bodyBytes.Length / 1MB, 2)
Write-Host "  Payload size: $sizeMB MB" -ForegroundColor Yellow

Write-Host "=== Step 3: Sending request to {url} ===" -ForegroundColor Cyan
Write-Host "  This may take several minutes..."

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

try {{
    $response = Invoke-RestMethod -Uri '{url}' `
        -Method POST `
        -ContentType 'application/json' `
        -Body $jsonBody `
        -TimeoutSec 600
}} catch {{
    $stopwatch.Stop()
    Write-Error "Request failed after $($stopwatch.Elapsed.TotalSeconds.ToString('F1'))s: $_"
    exit 1
}}

$stopwatch.Stop()
$elapsed = $stopwatch.Elapsed.TotalSeconds.ToString('F1')
Write-Host "  Response received in ${{elapsed}}s" -ForegroundColor Green

Write-Host "=== Step 4: Validating response ===" -ForegroundColor Cyan

$expectedKeys = @({", ".join(f"'{k}'" for k in _RESPONSE_EXPECTED_KEYS)})
$responseObj = $response
if ($response -is [string]) {{
    $responseObj = $response | ConvertFrom-Json
}}

$missing = @()
foreach ($key in $expectedKeys) {{
    if (-not ($responseObj.PSObject.Properties.Name -contains $key)) {{
        $missing += $key
    }}
}}

if ($missing.Count -gt 0) {{
    Write-Warning "Response is missing expected fields: $($missing -join ', ')"
    Write-Warning "The response may indicate an error from the server."
}} else {{
    Write-Host "  All expected fields present in response." -ForegroundColor Green

    # Check batchimages in response
    $batchImgs = $responseObj.batchimages
    if ($null -eq $batchImgs -or $batchImgs.Count -eq 0) {{
        Write-Warning "Response 'batchimages' is empty — server may have rejected the images."
    }} else {{
        Write-Host "  batchimages contains $($batchImgs.Count) result(s)." -ForegroundColor Green
    }}
}}

Write-Host "=== Step 5: Saving response ===" -ForegroundColor Cyan

$outputFile = "batch_response_{FirstName}_{LastName}.json"
$responseObj | ConvertTo-Json -Depth 10 | Set-Content -Path $outputFile -Encoding UTF8
Write-Host "  Saved to: $outputFile" -ForegroundColor Green
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
'''

        # Build bash script
        bash_image_blocks = []
        for i, p in enumerate(image_paths):
            safe_p = p.replace("'", "'\\''")
            img_name = p.replace("\\", "/").split("/")[-1]
            bash_image_blocks.append(
                f'  # Image {i+1}\n'
                f"  IMG_PATH_{i}='{safe_p}'\n"
                f'  if [ ! -f "$IMG_PATH_{i}" ]; then echo "ERROR: Image not found: $IMG_PATH_{i}"; exit 1; fi\n'
                f'  B64_{i}=$(base64 -w 0 "$IMG_PATH_{i}")\n'
                f'  IMAGES+=\',{{"ImageName":"{img_name}","Image64":"\'\'$B64_{i}\'\'"}}\''
            )

        bash_meta_fields = ", ".join(
            f'"{k}":"{v}"' for k, v in metadata.items()
        )
        bash_expected_keys = " ".join(f'"{k}"' for k in _RESPONSE_EXPECTED_KEYS)

        bash_script = f'''#!/usr/bin/env bash
# ── Batch AI Assessment ──
# Endpoint: {url}
# Patient: {FirstName} {LastName}
# Images: {len(image_paths)}

set -euo pipefail

echo "=== Step 1: Reading and encoding images ==="

IMAGES=""
{chr(10).join(bash_image_blocks)}
# Remove leading comma
IMAGES="${{IMAGES#,}}"

echo "  Encoded {len(image_paths)} image(s) successfully."

echo "=== Step 2: Building request payload ==="

BODY='{{{bash_meta_fields},"batchimages":['$IMAGES']}}'
SIZE=$(echo -n "$BODY" | wc -c)
SIZE_MB=$(echo "scale=2; $SIZE / 1048576" | bc)
echo "  Payload size: ${{SIZE_MB}} MB"

echo "=== Step 3: Sending request to {url} ==="
echo "  This may take several minutes..."

START=$(date +%s)

RESPONSE=$(curl -s -w "\\n%{{http_code}}" -X POST '{url}' \\
  -H 'Content-Type: application/json' \\
  -d "$BODY" \\
  --max-time 600)

END=$(date +%s)
ELAPSED=$((END - START))
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY_RESP=$(echo "$RESPONSE" | sed '$d')

echo "  Response received in ${{ELAPSED}}s (HTTP $HTTP_CODE)"

if [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
  echo "ERROR: Server returned HTTP $HTTP_CODE"
  echo "$BODY_RESP"
  exit 1
fi

echo "=== Step 4: Validating response ==="

EXPECTED_KEYS=({bash_expected_keys})
VALID=true
for KEY in "${{EXPECTED_KEYS[@]}}"; do
  if ! echo "$BODY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$KEY' in d" 2>/dev/null; then
    echo "  WARNING: Missing expected field: $KEY"
    VALID=false
  fi
done

if [ "$VALID" = true ]; then
  echo "  All expected fields present in response."
  BATCH_COUNT=$(echo "$BODY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('batchimages',[])))")
  echo "  batchimages contains $BATCH_COUNT result(s)."
fi

echo "=== Step 5: Saving response ==="

OUTPUT_FILE="batch_response_{FirstName}_{LastName}.json"
echo "$BODY_RESP" | python3 -m json.tool > "$OUTPUT_FILE"
echo "  Saved to: $OUTPUT_FILE"
echo ""
echo "=== Done ==="
'''

        return json.dumps({
            "instruction": (
                f"Run ONE of the scripts below to send the batch assessment for "
                f"patient {FirstName} {LastName} ({len(image_paths)} images) to {ep['name']}. "
                f"Use PowerShell on Windows or bash on Linux/macOS. "
                f"The script encodes images, sends the request, validates the response, "
                f"and saves results to batch_response_{FirstName}_{LastName}.json."
            ),
            "powershell": ps_script,
            "bash": bash_script,
        }, indent=2)

    @mcp.tool()
    def list_batch_endpoints() -> str:
        """List available endpoints and ask the user to choose one via buttons.

        Call this FIRST in any batch assessment workflow. It loads the available
        endpoints from the config file and instructs the assistant to present them
        to the user as clickable buttons using vscode_askQuestions.

        Always present 'ai-cluster' as the recommended default.
        """
        endpoints = _load_endpoints()
        result = [
            {"name": key, "url": ep["url"], "requirements": ep["requirements"]}
            for key, ep in endpoints.items()
        ]
        return json.dumps({
            "endpoints": result,
            "default": _DEFAULT_ENDPOINT,
            "instruction": (
                "Call vscode_askQuestions immediately with the question and options below "
                "to let the user pick an endpoint via buttons. "
                "The recommended default is 'ai-cluster'. "
                "After the user selects, proceed with validate_batch_request."
            ),
            "question": {
                "header": "Select AI Endpoint",
                "question": "Which endpoint should be used for the batch AI assessment?",
                "options": _endpoint_options(),
                "allowFreeformInput": True,
            },
        }, indent=2)
