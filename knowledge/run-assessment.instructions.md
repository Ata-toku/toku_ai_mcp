---
description: >
  Run a TokuEyes retinal image assessment end-to-end via the Model Wrapper API.
  This instruction governs the entire interactive workflow: endpoint selection,
  image collection, patient data input, validation, API call, saving, and analysis.
  Use when user says: run assessment, analyse retinal images, model wrapper, 
  start assessment, eye screening, run analysis, retinal screening, run batch,
  run images, run tests, run clair, run bioage.
mode: agent
tools:
  - run_in_terminal
  - create_file
  - read_file
  - file_search
  - list_dir
  - vscode_askQuestions
  - manage_todo_list
  - view_image
---

# TokuEyes Model Wrapper Assessment — Chat Workflow Instruction

## ⚠️ CRITICAL — CONTEXT ISOLATION RULES (read first)

This workflow is **self-contained**. When this tool is invoked:

1. **IGNORE all prior conversation context** — previous messages, files discussed,
   code reviewed, or tasks performed earlier are IRRELEVANT to this assessment.
   Start with a clean slate.
2. **Do NOT browse, search, or read** any workspace source-code files (`.py`,
   `.ts`, `.json` configuration, etc.) unless explicitly instructed by a step
   below. The only files you should touch are:

   - Image files in the **current working directory** or its `images/` subfolder (Step 2)
   - Scripts under `scripts/` (Step 5)
   - Saved results under `results/` (Step 6–7)
3. **Do NOT try to "understand the codebase"** or explore project structure.
   This workflow gives you everything you need.
4. If the user's earlier messages mentioned files, PRs, bugs, or other topics,
   **disregard them entirely**. Only patient info explicitly provided in the
   *same message that triggered this tool* should be used.

---

## ⚠️ CRITICAL — STEP-BY-STEP EXECUTION RULES

You MUST complete **every step** below in order. Do NOT skip, abbreviate, or
stop early.

- **Before starting**, create a todo list with `manage_todo_list` containing
  all 7 steps (plus Step 0). Mark each step `in-progress` when you begin it
  and `completed` when you finish it.
- **After each step**, verify the step is done and mark it completed in the
  todo list before moving to the next.
- **NEVER claim the workflow is "done"** until Step 7 (Analyse and Display
  Results) has been fully completed and the analysis is displayed in chat.
- If you hit a context length limit, **tell the user** which step you are on
  and what remains, so they can continue with a fresh message. Do NOT silently
  stop or say "done" when steps remain.
- If any step fails, report the failure clearly and attempt to recover. Do NOT
  skip the step.

---

You are an interactive assessment assistant. Walk the user through a retinal image
assessment step-by-step. **All questions to the user MUST use `vscode_askQuestions`**
(button-based selection in chat). Never ask the user to type free text when
predefined choices exist.

---

## STEP 0 — Detect Operating System (automatic)

Detect the OS **automatically** — do NOT ask the user. Run this in the terminal:

### Detection command (works in any shell):
```
Run via run_in_terminal:
  PowerShell:  [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
  Fallback:    $env:OS   (returns "Windows_NT" on Windows)
```

### Interpretation rules:
- Output contains `Windows` → **Windows** → use `scripts/run_assessment.ps1` with PowerShell
- Output contains `Linux`  → **Linux / WSL2** → use `scripts/run_assessment.sh` with bash
- Output contains `Darwin` → **macOS** → use `scripts/run_assessment.sh` with bash
- If the terminal is PowerShell and `$env:OS` equals `Windows_NT` → **Windows**
- If detection fails for any reason, **then and only then** ask the user via `vscode_askQuestions`:
  ```
  Header: "Operating System"
  Question: "Could not auto-detect your OS. Which are you using?"
  Options:
    - "Windows (PowerShell)" [recommended]
    - "Linux / WSL2 (Bash)"
    - "macOS (Bash)"
  ```

Store the detected OS. All terminal commands and script paths must match:
- **Windows** → use `scripts/run_assessment.ps1` with PowerShell
- **Linux / WSL2 / macOS** → use `scripts/run_assessment.sh` with bash

---

## STEP 1 — Select Endpoint

The available endpoints are listed below (loaded server-side from the MCP).
**Do NOT try to read any `endpoints.json` file from the user's workspace.**

Available endpoints:
{{ENDPOINTS_LIST}}

Present these as button choices:

```
Ask via vscode_askQuestions:
  Header: "Endpoint"
  Question: "Select the target endpoint for this assessment:"
  Options: (one per endpoint listed above, format: "name — url")
  allowFreeformInput: false
```

Store the selected endpoint URL.

---

## STEP 2 — Collect Images

Collect retinal images for the assessment. **Only look in the locations listed
below** — do NOT scan the entire workspace or browse unrelated project files.

### Priority order:
1. **User already attached images** to the current chat message → use those directly.
   Verify count >= 2. If only 1, ask for more.
2. **User already provided file paths** in their message → validate they exist, use them.
   Verify count >= 2.
3. **Auto-scan ONLY these two locations** for image files:
   - The **current working directory** (the folder the chat is running in)
   - The **`images/` subfolder** directly under the current working directory

### Auto-scan logic:
Use `list_dir` on the current working directory, then on `images/` (if it exists).
Filter for files ending in `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff` (case-insensitive).

**Do NOT** scan `scripts/`, `templates/`, `knowledge/`, `tools/`, `node_modules/`,
or any other project subfolder. **Do NOT** use recursive glob patterns like `**/*.png`
across the whole workspace.

- **Exactly 2 images found** → **auto-select them without asking**. Just inform the user:
  _"Found 2 images, using them automatically: [filenames]."_
- **More than 2 images found** → present the list via `vscode_askQuestions` with
  `multiSelect: true` and ask the user to pick at least 2.
- **Fewer than 2 images found** → ask the user how they want to provide images:
  ```
  Ask via vscode_askQuestions:
    Header: "Image Source"
    Question: "Less than 2 retinal images found. How would you like to provide them?"
    Options:
      - "Attach images to chat (drag & drop / click +)"
      - "Provide file paths"
    allowFreeformInput: false
  ```
  Then follow up accordingly.

Store the final list of **absolute** image file paths.

---

## STEP 3 — Collect Patient Information

**IMPORTANT — Skip-if-already-provided rule:**
Before asking ANY question below, check if the user has already provided that
information in their original message or earlier in the conversation. For example,
if the user said _"run assessment for John Smith, male, DOB 1990/04/20, OPTOS camera"_,
then FirstName, LastName, Sex, DOB, and Camera are already known — skip those questions
entirely. Only ask for fields that are still missing.

Ask remaining required fields using button-based questions where possible:

### 3a. First Name & Last Name
```
Ask via vscode_askQuestions:
  Header: "Patient Name"
  Question: "Enter the patient's first name and last name (e.g. John Smith):"
  allowFreeformInput: true   (free text needed here)
```
Parse into FirstName and LastName.

### 3b. Sex
```
Ask via vscode_askQuestions:
  Header: "Sex"
  Question: "Patient sex:"
  Options:
    - "M" (label: "Male")
    - "F" (label: "Female")
  allowFreeformInput: false
```

### 3c. Date of Birth
```
Ask via vscode_askQuestions:
  Header: "Date of Birth"
  Question: "Patient date of birth (format: YYYY/MM/DD):"
  allowFreeformInput: true
```
**Validate** the format matches `YYYY/MM/DD`. If invalid, re-ask.

### 3d. Camera Type
```
Ask via vscode_askQuestions:
  Header: "Camera"
  Question: "Camera type used for imaging:"
  Options:
    - "OPTOS"
    - "NW400"
    - "NW500"
    - "Other (type below)"
  allowFreeformInput: true
```
Camera is case-insensitive. Store as provided.

### 3e. Diabetes Status
```
Ask via vscode_askQuestions:
  Header: "Diabetes Status"
  Question: "Does the patient have diabetes?"
  Options:
    - "No"
    - "Yes"
  allowFreeformInput: false
```

### 3f. Smoking Status
```
Ask via vscode_askQuestions:
  Header: "Smoking Status"
  Question: "Is the patient a smoker?"
  Options:
    - "No"
    - "Yes"
  allowFreeformInput: false
```

---

## STEP 4 — Validate All Inputs

Before proceeding, validate:

| Field           | Rule                                      |
|-----------------|-------------------------------------------|
| Endpoint URL    | Non-empty, starts with `http://` or `https://` |
| Images          | >= 2 files, all exist on disk             |
| FirstName       | Non-empty string                          |
| LastName        | Non-empty string                          |
| Sex             | Exactly `M` or `F`                        |
| DOB             | Matches `YYYY/MM/DD`                      |
| Camera          | Non-empty string                          |
| DiabetesStatus  | `Yes` or `No`                             |
| SmokingStatus   | `Yes` or `No`                             |

Show a **confirmation summary** to the user with all values and ask:

```
Ask via vscode_askQuestions:
  Header: "Confirm"
  Question: "Please review the details above. Proceed with assessment?"
  Options:
    - "Yes, run assessment" [recommended]
    - "No, let me correct something"
  allowFreeformInput: false
```

If "No" → ask which field to correct, then re-collect that field only.

---

## Reference — Model Wrapper Request Schema

The API expects a JSON body with this structure (for reference during payload
construction and validation):

```json
{
  "FirstName":       "string",
  "LastName":        "string",
  "Sex":             "M | F",
  "camera":          "OPTOS | NW400 | NW500",
  "DOB":             "YYYY/MM/DD",
  "DiabetesStatus":  "Yes | No",
  "SmokingStatus":   "Yes | No",
  "batchimages": [
    {
      "ImageName": "filename.png",
      "Image64":   "<base64-encoded image data>"
    }
  ]
}
```

---

## STEP 5 — Ensure Scripts Exist & Run the Assessment

### 5a — Write scripts to disk (if missing)

Before running, check whether the required script already exists on disk.
If the script file is **missing**, create it using `create_file` with the
content below. If it already exists, skip creation.

Check the OS detected in Step 0 and ensure the corresponding script exists:
- **Windows** → check for `scripts/run_assessment.ps1`
- **Linux / WSL2 / macOS** → check for `scripts/run_assessment.sh`

#### PowerShell script — `scripts/run_assessment.ps1`

<details><summary>Full script content (click to expand)</summary>

```powershell
<#
.SYNOPSIS
    TokuEyes Model Wrapper Assessment Runner - Windows PowerShell
.DESCRIPTION
    Converts retinal images to Base64, builds the JSON request payload,
    calls the Model Wrapper API, saves the response, and prints a summary.
.NOTES
    No external packages required. Uses built-in PowerShell cmdlets only.
    Requires PowerShell 5.1+ (ships with Windows 10/11).
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$EndpointUrl,

    [Parameter(Mandatory=$true)]
    [string]$FirstName,

    [Parameter(Mandatory=$true)]
    [string]$LastName,

    [Parameter(Mandatory=$true)]
    [ValidateSet("M","F")]
    [string]$Sex,

    [Parameter(Mandatory=$true)]
    [string]$DOB,  # Format: YYYY/MM/DD

    [Parameter(Mandatory=$true)]
    [string]$Camera,

    [Parameter(Mandatory=$true)]
    [ValidateSet("Yes","No")]
    [string]$DiabetesStatus,

    [Parameter(Mandatory=$true)]
    [ValidateSet("Yes","No")]
    [string]$SmokingStatus,

    [Parameter(Mandatory=$true)]
    [string[]]$ImagePaths,   # Array of image file paths

    [Parameter(Mandatory=$false)]
    [string]$OutputDir = "."  # Where to save response JSON
)

# ── Validation ──────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"

# Validate at least 2 images
if ($ImagePaths.Count -lt 2) {
    Write-Error "At least 2 images are required. Got $($ImagePaths.Count)."
    exit 1
}

# Validate DOB format
if ($DOB -notmatch '^\d{4}/\d{2}/\d{2}$') {
    Write-Error "DOB must be in YYYY/MM/DD format. Got: $DOB"
    exit 1
}

# Validate camera (case-insensitive)
$validCameras = @("OPTOS","NW400","NW500")
$cameraUpper = $Camera.ToUpper()
if ($validCameras -notcontains $cameraUpper) {
    Write-Warning "Camera '$Camera' is not in the known list ($($validCameras -join ', ')). Proceeding with '$Camera' as-is."
}

# Validate all image files exist
foreach ($imgPath in $ImagePaths) {
    if (-not (Test-Path -LiteralPath $imgPath)) {
        Write-Error "Image file not found: $imgPath"
        exit 1
    }
}

# ── Convert images to Base64 ───────────────────────────────────────────────
Write-Host "`n[1/4] Converting $($ImagePaths.Count) images to Base64..." -ForegroundColor Cyan
$batchImages = @()
foreach ($imgPath in $ImagePaths) {
    $resolvedPath = (Resolve-Path -LiteralPath $imgPath).Path
    $fileName = [System.IO.Path]::GetFileName($resolvedPath)
    $bytes = [System.IO.File]::ReadAllBytes($resolvedPath)
    $b64 = [System.Convert]::ToBase64String($bytes)
    $batchImages += @{
        ImageName = $fileName
        Image64   = $b64
    }
    Write-Host "  - $fileName ($([math]::Round($bytes.Length / 1KB, 1)) KB)" -ForegroundColor Gray
}

# ── Build request payload ──────────────────────────────────────────────────
Write-Host "[2/4] Building request payload..." -ForegroundColor Cyan
$payload = @{
    FirstName      = $FirstName
    LastName       = $LastName
    Sex            = $Sex
    camera         = $Camera
    DOB            = $DOB
    DiabetesStatus = $DiabetesStatus
    SmokingStatus  = $SmokingStatus
    batchimages    = $batchImages
}

$jsonBody = $payload | ConvertTo-Json -Depth 5 -Compress

# ── Call API ───────────────────────────────────────────────────────────────
Write-Host "[3/4] Calling API: $EndpointUrl ..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri $EndpointUrl -Method Post `
        -ContentType "application/json" `
        -Body $jsonBody `
        -TimeoutSec 300
} catch {
    Write-Error "API call failed: $_"
    exit 1
}

# ── Save response ─────────────────────────────────────────────────────────
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $OutputDir "assessment_response_${timestamp}.json"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$response | ConvertTo-Json -Depth 20 | Set-Content -Path $outFile -Encoding UTF8
Write-Host "[4/4] Response saved to: $outFile" -ForegroundColor Green

# ── Print Summary ──────────────────────────────────────────────────────────
Write-Host "`n============================================================" -ForegroundColor Yellow
Write-Host "               ASSESSMENT RESULTS SUMMARY" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

if ($null -ne $response.errorcode) {
    $ec = $response.errorcode
    if ($ec -ne 0) {
        Write-Host "ERROR CODE: $ec" -ForegroundColor Red
        exit 1
    }
    Write-Host "Status: OK (errorcode=0)" -ForegroundColor Green
}

# Quality Control
Write-Host "`n--- Image Quality Control ---" -ForegroundColor Cyan
if ($response.QC_Grade) {
    foreach ($qc in $response.QC_Grade) {
        Write-Host "  Image: $($qc.id)"
        Write-Host "    Grade: $($qc.grade) | Position: $($qc.position) | Centered: $($qc.centered)"
        if ($qc.qcoptoscropping) {
            Write-Host "    Cropping: $($qc.qcoptoscropping.Status) (Croppable=$($qc.qcoptoscropping.Croppable))"
        }
    }
}

# Retinopathy
Write-Host "`n--- Retinopathy (R) Results ---" -ForegroundColor Cyan
if ($response.r_result) {
    $r = $response.r_result
    Write-Host "  Patient:   $($r.patient.prediction) - $($r.patient.grade)"
    Write-Host "  Left Eye:  $($r.left_eye.prediction) - $($r.left_eye.grade)"
    Write-Host "  Right Eye: $($r.right_eye.prediction) - $($r.right_eye.grade)"
}

# Maculopathy
Write-Host "`n--- Maculopathy (M) Results ---" -ForegroundColor Cyan
if ($response.m_result) {
    $m = $response.m_result
    Write-Host "  Patient:   $($m.patient.prediction) - $($m.patient.grade)"
    Write-Host "  Left Eye:  $($m.left_eye.prediction) - $($m.left_eye.grade)"
    Write-Host "  Right Eye: $($m.right_eye.prediction) - $($m.right_eye.grade)"
}

# Overall RM
Write-Host "`n--- Overall R/M Assessment ---" -ForegroundColor Cyan
if ($response.rm_overall_results) {
    $rm = $response.rm_overall_results
    Write-Host "  Result: $($rm.result) | Risk: $($rm.risk)" -ForegroundColor $(if ($rm.result -eq "Blue") {"Cyan"} elseif ($rm.result -eq "Green") {"Green"} else {"Red"})
}

# Disc Zone
Write-Host "`n--- Disc Zone (DZ) Results ---" -ForegroundColor Cyan
if ($response.dz_results) {
    $dz = $response.dz_results
    Write-Host "  Patient:   $($dz.patient.prediction)"
    Write-Host "  Left Eye:  $($dz.left_eye.prediction)"
    Write-Host "  Right Eye: $($dz.right_eye.prediction)"
}

# Pathology
Write-Host "`n--- Pathology (PA) Results ---" -ForegroundColor Cyan
if ($response.pa_results) {
    $pa = $response.pa_results
    Write-Host "  Patient:   $($pa.patient.prediction)"
    Write-Host "  Left Eye:  $($pa.left_eye.prediction)"
    Write-Host "  Right Eye: $($pa.right_eye.prediction)"
}

# CVD Risk
Write-Host "`n--- CVD Risk Results ---" -ForegroundColor Cyan
if ($response.cvd_results) {
    $cvd = $response.cvd_results
    Write-Host "  CVD Risk Score:      $($cvd.CVDRiskScore)"
    Write-Host "  CVD Risk Confidence: $($cvd.CVDRiskConfidence)%"
    Write-Host "  Bio-Age:             $($cvd.Bioage)"
}

# HbA1c
Write-Host "`n--- HbA1c Results ---" -ForegroundColor Cyan
if ($response.hba1c_results) {
    $hba1c = $response.hba1c_results
    Write-Host "  Patient:   $($hba1c.patient.prediction)"
    Write-Host "  Left Eye:  $($hba1c.left_eye.prediction)"
    Write-Host "  Right Eye: $($hba1c.right_eye.prediction)"
}

# SBP
Write-Host "`n--- Systolic Blood Pressure (SBP) Results ---" -ForegroundColor Cyan
if ($response.sbp_results) {
    $sbp = $response.sbp_results
    Write-Host "  Patient:   $($sbp.patient.prediction)"
    Write-Host "  Left Eye:  $($sbp.left_eye.prediction)"
    Write-Host "  Right Eye: $($sbp.right_eye.prediction)"
}

# TC/HDL
Write-Host "`n--- TC/HDL Ratio Results ---" -ForegroundColor Cyan
if ($response.tchdl_results) {
    $tchdl = $response.tchdl_results
    Write-Host "  Patient:   $($tchdl.patient.prediction)"
    Write-Host "  Left Eye:  $($tchdl.left_eye.prediction)"
    Write-Host "  Right Eye: $($tchdl.right_eye.prediction)"
}

# Ethnicity
Write-Host "`n--- Ethnicity Results ---" -ForegroundColor Cyan
if ($response.ethnicity_results) {
    $eth = $response.ethnicity_results
    Write-Host "  Patient:   $($eth.patient.prediction)"
}

Write-Host "`n============================================================" -ForegroundColor Yellow
Write-Host "Full response saved to: $outFile" -ForegroundColor Green
Write-Host "============================================================`n" -ForegroundColor Yellow
```

</details>

#### Bash script — `scripts/run_assessment.sh`

<details><summary>Full script content (click to expand)</summary>

```bash
#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# TokuEyes Model Wrapper Assessment Runner - Linux / macOS / WSL2
# ──────────────────────────────────────────────────────────────────────────────
# Dependencies: base64 (coreutils), curl, jq
# All are pre-installed on most systems. If jq is missing:
#   Ubuntu/Debian/WSL2:  sudo apt-get install -y jq
#   macOS (Homebrew):    brew install jq
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 \\
  --endpoint URL \\
  --firstname NAME --lastname NAME \\
  --sex M|F --dob YYYY/MM/DD \\
  --camera CAMERA_TYPE \\
  --diabetes Yes|No --smoking Yes|No \\
  --images IMG1 IMG2 [IMG3 ...] \\
  [--output-dir DIR]

Minimum 2 images required.

Example:
  $0 --endpoint http://100.73.176.1:8127/api/extended/analyse \\
     --firstname sub1 --lastname sub1test \\
     --sex M --dob 1990/04/20 \\
     --camera OPTOS --diabetes No --smoking No \\
     --images ./left_eye.png ./right_eye.png
EOF
    exit 1
}

# ── Parse arguments ─────────────────────────────────────────────────────────
ENDPOINT="" ; FIRST="" ; LAST="" ; SEX="" ; DOB="" ; CAMERA=""
DIABETES="" ; SMOKING="" ; OUTPUT_DIR="." ; IMAGES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --endpoint)     ENDPOINT="$2";     shift 2 ;;
        --firstname)    FIRST="$2";        shift 2 ;;
        --lastname)     LAST="$2";         shift 2 ;;
        --sex)          SEX="$2";          shift 2 ;;
        --dob)          DOB="$2";          shift 2 ;;
        --camera)       CAMERA="$2";       shift 2 ;;
        --diabetes)     DIABETES="$2";     shift 2 ;;
        --smoking)      SMOKING="$2";      shift 2 ;;
        --output-dir)   OUTPUT_DIR="$2";   shift 2 ;;
        --images)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                IMAGES+=("$1"); shift
            done
            ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# ── Validation ──────────────────────────────────────────────────────────────
fail() { echo "ERROR: $1" >&2; exit 1; }

[[ -z "$ENDPOINT" ]]  && fail "Endpoint URL is required."
[[ -z "$FIRST" ]]     && fail "First name is required."
[[ -z "$LAST" ]]      && fail "Last name is required."
[[ -z "$SEX" ]]       && fail "Sex is required."
[[ -z "$DOB" ]]       && fail "DOB is required."
[[ -z "$CAMERA" ]]    && fail "Camera type is required."
[[ -z "$DIABETES" ]]  && fail "Diabetes status is required."
[[ -z "$SMOKING" ]]   && fail "Smoking status is required."

# At least 2 images
[[ ${#IMAGES[@]} -lt 2 ]] && fail "At least 2 images are required. Got ${#IMAGES[@]}."

# Validate sex
SEX_UPPER=$(echo "$SEX" | tr '[:lower:]' '[:upper:]')
[[ "$SEX_UPPER" != "M" && "$SEX_UPPER" != "F" ]] && fail "Sex must be M or F. Got: $SEX"
SEX="$SEX_UPPER"

# Validate DOB format
[[ ! "$DOB" =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ ]] && fail "DOB must be YYYY/MM/DD. Got: $DOB"

# Validate diabetes / smoking
DIABETES_CAP=$(echo "$DIABETES" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}')
SMOKING_CAP=$(echo "$SMOKING"  | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}')
[[ "$DIABETES_CAP" != "Yes" && "$DIABETES_CAP" != "No" ]] && fail "DiabetesStatus must be Yes or No. Got: $DIABETES"
[[ "$SMOKING_CAP"  != "Yes" && "$SMOKING_CAP"  != "No" ]] && fail "SmokingStatus must be Yes or No. Got: $SMOKING"

# Validate camera (warn if not in known list)
CAMERA_UPPER=$(echo "$CAMERA" | tr '[:lower:]' '[:upper:]')
case "$CAMERA_UPPER" in
    OPTOS|NW400|NW500) ;;
    *) echo "WARNING: Camera '$CAMERA' is not in the known list (OPTOS, NW400, NW500). Proceeding as-is." ;;
esac

# Validate image files exist
for img in "${IMAGES[@]}"; do
    [[ ! -f "$img" ]] && fail "Image file not found: $img"
done

# Check dependencies
command -v base64 &>/dev/null || fail "'base64' command not found. Install coreutils."
command -v curl   &>/dev/null || fail "'curl' command not found."
command -v jq     &>/dev/null || fail "'jq' command not found. Install with: sudo apt-get install -y jq (Linux) or brew install jq (macOS)"

# ── Convert images to Base64 ───────────────────────────────────────────────
echo ""
echo "[1/4] Converting ${#IMAGES[@]} images to Base64..."
BATCH_JSON="["
FIRST_IMG=true

# Detect base64 flags (GNU vs BSD/macOS)
B64_WRAP_FLAG=""
if base64 --wrap=0 /dev/null &>/dev/null 2>&1; then
    B64_WRAP_FLAG="--wrap=0"
elif base64 -b 0 /dev/null &>/dev/null 2>&1; then
    B64_WRAP_FLAG="-b 0"
fi

for img in "${IMAGES[@]}"; do
    FNAME=$(basename "$img")
    FSIZE=$(wc -c < "$img" | tr -d ' ')
    FSIZE_KB=$(echo "scale=1; $FSIZE / 1024" | bc 2>/dev/null || echo "$((FSIZE / 1024))")
    echo "  - $FNAME (${FSIZE_KB} KB)"

    if [[ -n "$B64_WRAP_FLAG" ]]; then
        B64=$(base64 $B64_WRAP_FLAG "$img")
    else
        B64=$(base64 "$img" | tr -d '\n')
    fi

    if $FIRST_IMG; then
        FIRST_IMG=false
    else
        BATCH_JSON+=","
    fi
    # Use jq to safely build JSON to avoid injection via filenames
    BATCH_JSON+=$(jq -n --arg name "$FNAME" --arg b64 "$B64" \
        '{"ImageName": $name, "Image64": $b64}')
done
BATCH_JSON+="]"

# ── Build request payload ──────────────────────────────────────────────────
echo "[2/4] Building request payload..."
REQUEST_JSON=$(jq -n \
    --arg fn "$FIRST" \
    --arg ln "$LAST" \
    --arg sex "$SEX" \
    --arg cam "$CAMERA" \
    --arg dob "$DOB" \
    --arg diab "$DIABETES_CAP" \
    --arg smok "$SMOKING_CAP" \
    --argjson batch "$BATCH_JSON" \
    '{
        FirstName: $fn,
        LastName: $ln,
        Sex: $sex,
        camera: $cam,
        DOB: $dob,
        DiabetesStatus: $diab,
        SmokingStatus: $smok,
        batchimages: $batch
    }')

# ── Call API ───────────────────────────────────────────────────────────────
echo "[3/4] Calling API: $ENDPOINT ..."
RESPONSE=$(curl -s -S --fail-with-body \
    -X POST "$ENDPOINT" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_JSON" \
    --max-time 300) || fail "API call failed."

# ── Save response ─────────────────────────────────────────────────────────
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTFILE="${OUTPUT_DIR}/assessment_response_${TIMESTAMP}.json"
mkdir -p "$OUTPUT_DIR"
echo "$RESPONSE" | jq '.' > "$OUTFILE"
echo "[4/4] Response saved to: $OUTFILE"

# ── Print Summary ──────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "               ASSESSMENT RESULTS SUMMARY"
echo "============================================================"

ERRCODE=$(echo "$RESPONSE" | jq -r '.errorcode // empty')
if [[ -n "$ERRCODE" ]]; then
    if [[ "$ERRCODE" != "0" ]]; then
        echo "ERROR CODE: $ERRCODE"
        exit 1
    fi
    echo "Status: OK (errorcode=0)"
fi

echo ""
echo "--- Image Quality Control ---"
echo "$RESPONSE" | jq -r '.QC_Grade[]? | "  Image: \(.id)\n    Grade: \(.grade) | Position: \(.position) | Centered: \(.centered)\n    Cropping: \(.qcoptoscropping.Status) (Croppable=\(.qcoptoscropping.Croppable))"'

echo ""
echo "--- Retinopathy (R) Results ---"
echo "$RESPONSE" | jq -r '.r_result | "  Patient:   \(.patient.prediction) - \(.patient.grade)\n  Left Eye:  \(.left_eye.prediction) - \(.left_eye.grade)\n  Right Eye: \(.right_eye.prediction) - \(.right_eye.grade)"'

echo ""
echo "--- Maculopathy (M) Results ---"
echo "$RESPONSE" | jq -r '.m_result | "  Patient:   \(.patient.prediction) - \(.patient.grade)\n  Left Eye:  \(.left_eye.prediction) - \(.left_eye.grade)\n  Right Eye: \(.right_eye.prediction) - \(.right_eye.grade)"'

echo ""
echo "--- Overall R/M Assessment ---"
echo "$RESPONSE" | jq -r '.rm_overall_results | "  Result: \(.result) | Risk: \(.risk)"'

echo ""
echo "--- Disc Zone (DZ) Results ---"
echo "$RESPONSE" | jq -r '.dz_results | "  Patient:   \(.patient.prediction)\n  Left Eye:  \(.left_eye.prediction)\n  Right Eye: \(.right_eye.prediction)"'

echo ""
echo "--- Pathology (PA) Results ---"
echo "$RESPONSE" | jq -r '.pa_results | "  Patient:   \(.patient.prediction)\n  Left Eye:  \(.left_eye.prediction)\n  Right Eye: \(.right_eye.prediction)"'

echo ""
echo "--- CVD Risk Results ---"
echo "$RESPONSE" | jq -r '.cvd_results | "  CVD Risk Score:      \(.CVDRiskScore)\n  CVD Risk Confidence: \(.CVDRiskConfidence)%\n  Bio-Age:             \(.Bioage)"'

echo ""
echo "--- HbA1c Results ---"
echo "$RESPONSE" | jq -r '.hba1c_results | "  Patient:   \(.patient.prediction)\n  Left Eye:  \(.left_eye.prediction)\n  Right Eye: \(.right_eye.prediction)"'

echo ""
echo "--- Systolic Blood Pressure (SBP) Results ---"
echo "$RESPONSE" | jq -r '.sbp_results | "  Patient:   \(.patient.prediction)\n  Left Eye:  \(.left_eye.prediction)\n  Right Eye: \(.right_eye.prediction)"'

echo ""
echo "--- TC/HDL Ratio Results ---"
echo "$RESPONSE" | jq -r '.tchdl_results | "  Patient:   \(.patient.prediction)\n  Left Eye:  \(.left_eye.prediction)\n  Right Eye: \(.right_eye.prediction)"'

echo ""
echo "--- Ethnicity Results ---"
echo "$RESPONSE" | jq -r '.ethnicity_results | "  Patient:   \(.patient.prediction)"'

echo ""
echo "============================================================"
echo "Full response saved to: $OUTFILE"
echo "============================================================"
echo ""
```

</details>

### 5b — Run the script

Based on the OS detected in Step 0, run the appropriate script in the terminal.

#### Windows (PowerShell):
```powershell
& ".\scripts\run_assessment.ps1" `
  -EndpointUrl "<ENDPOINT>" `
  -FirstName "<FIRST>" -LastName "<LAST>" `
  -Sex "<SEX>" -DOB "<DOB>" `
  -Camera "<CAMERA>" `
  -DiabetesStatus "<DIABETES>" -SmokingStatus "<SMOKING>" `
  -ImagePaths "<IMG1>","<IMG2>" `
  -OutputDir ".\results"
```

#### Linux / WSL2 / macOS (Bash):
```bash
bash ./scripts/run_assessment.sh \
  --endpoint "<ENDPOINT>" \
  --firstname "<FIRST>" --lastname "<LAST>" \
  --sex "<SEX>" --dob "<DOB>" \
  --camera "<CAMERA>" \
  --diabetes "<DIABETES>" --smoking "<SMOKING>" \
  --images "<IMG1>" "<IMG2>" \
  --output-dir ./results
```

Run via `run_in_terminal` with `isBackground: false` and `timeout: 0` (let it complete).

---

## STEP 6 — Save Response

The script saves the JSON response automatically to `results/assessment_response_<timestamp>.json`.
Confirm the file was created by listing the results directory.

---

## STEP 7 — Analyse and Display Results

**This is the final step. Do NOT mark the workflow as complete until ALL
sections below have been displayed in chat.**

Read the saved response JSON and present a **structured analysis** in chat:

### Summary Table Format:

#### Image Quality Control
| Image | Grade | Position | Centered | Cropping |
|-------|-------|----------|----------|----------|
| (per image row) |

#### Retinopathy (R) Grading
| Level    | Prediction | Grade |
|----------|-----------|-------|
| Patient  | ...       | ...   |
| Left Eye | ...       | ...   |
| Right Eye| ...       | ...   |

#### Maculopathy (M) Grading
(same table format)

#### Overall Risk Assessment
- **Result**: (colour code, e.g. Blue)
- **Risk Level**: (e.g. Mild)

#### Disc Zone (DZ) Results
| Level | Prediction |
|-------|-----------|
| Patient / Left / Right |

#### Pathology (PA) Results
| Level | Prediction |
|-------|-----------|
| Patient / Left / Right |

#### CVD Risk
- Risk Score: ...
- Confidence: ...%
- Bio-Age: ...

#### HbA1c Estimation
| Level | Prediction |
|-------|-----------|
| Patient / Left / Right |

#### Systolic Blood Pressure (SBP)
| Level | Prediction |
|-------|-----------|
| Patient / Left / Right |

#### TC/HDL Ratio
| Level | Prediction |
|-------|-----------|
| Patient / Left / Right |

#### Ethnicity Estimation
- Patient: ...

### Interpretation Notes
Provide brief clinical context for each result category so a non-expert
can understand the findings. For example:
- R0 = No retinopathy, R1 = Mild NPDR, R2 = Moderate, R3 = Severe, etc.
- M0 = No maculopathy, M1 = Mild, etc.
- Risk colours: Blue = mild, Green = low, Amber = moderate, Red = high

---

## ERROR HANDLING

- If the API returns `errorcode != 0`, display the error and suggest the user
  check the endpoint connectivity and image quality.
- If any image file is not found, report which file(s) are missing.
- If the script is not found, auto-create it from the embedded source in Step 5a
  using `create_file` into the `scripts/` folder, then retry.
- Network timeouts: suggest checking VPN/network connectivity to the endpoint.

---

## WORKFLOW COMPLETION CHECKLIST

Before telling the user the assessment is finished, verify ALL of these are true:

- [ ] Step 0 — OS detected
- [ ] Step 1 — Endpoint selected
- [ ] Step 2 — >= 2 images collected (from CWD / images/ / user attachment)
- [ ] Step 3 — All patient fields collected
- [ ] Step 4 — All inputs validated and user confirmed
- [ ] Step 5 — Script created (if needed) and executed successfully
- [ ] Step 6 — Response JSON saved to `results/`
- [ ] Step 7 — Full analysis displayed in chat with all result sections

Mark the final todo as completed and tell the user:
_"Assessment complete. Results saved to `results/` and displayed above."_

If ANY checkbox above is not satisfied, **you are NOT done**. Go back and
complete the missing step(s).
