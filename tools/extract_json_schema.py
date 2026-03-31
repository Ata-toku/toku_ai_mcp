import json
import re


# Embeddable Python script for client-side schema extraction.
# This gets written to a temp file and executed on the client machine.
_CLIENT_SCHEMA_SCRIPT = r'''
import json, re, base64, sys, os

def _is_numeric(s):
    try: float(s); return True
    except: return False

def _is_int(s):
    try: int(s); return True
    except: return False

def _is_base64(s):
    st = s.strip()
    if len(st) < 64: return False
    if len(st) > 256:
        if not re.match(r'^[A-Za-z0-9+/\r\n]+$', st[:128]): return False
        if not re.match(r'^[A-Za-z0-9+/\r\n]+=*$', st[-128:]): return False
        return len(st) % 4 == 0
    return bool(re.match(r'^[A-Za-z0-9+/\r\n]{64,}={0,2}$', st))

def classify(v):
    s = {"type": "string"}
    if not v: s.update(format="empty_string"); return s
    if _is_base64(v): s.update(format="base64", description="Base64-encoded binary data", length=len(v), decoded_size_approx=len(v)*3//4, example=v[:40]+"..."); return s
    if _is_int(v) and (not v.startswith("0") or v=="0"): s.update(format="integer_as_string", example=v); return s
    if _is_numeric(v): s.update(format="number_as_string", example=v); return s
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',v,re.I): s.update(format="uuid", example=v); return s
    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}',v): s.update(format="date-time", example=v); return s
    if re.match(r'^\d{4}-\d{2}-\d{2}$',v): s.update(format="date", example=v); return s
    if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$',v): s.update(format="email", example=v); return s
    if re.match(r'^https?://',v,re.I): s.update(format="uri", example=v); return s
    s["example"] = v[:100]+"..." if len(v)>200 else v
    return s

def extract(v, k=None):
    if v is None: return {"type":"null"}
    if isinstance(v, bool): return {"type":"boolean","example":v}
    if isinstance(v, int): return {"type":"integer","example":v}
    if isinstance(v, float): return {"type":"number","example":v}
    if isinstance(v, str): return classify(v)
    if isinstance(v, list):
        s = {"type":"array","length":len(v)}
        s["items"] = extract(v[0],k) if v else {}
        return s
    if isinstance(v, dict): return {"type":"object","properties":{kk:extract(vv,kk) for kk,vv in v.items()}}
    return {"type":"unknown"}

inp = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else None
data = json.loads(open(inp, encoding="utf-8").read())
result = json.dumps(extract(data), indent=2)
if out:
    open(out, "w", encoding="utf-8").write(result)
    print(f"Schema saved to {out}")
else:
    print(result)
'''


def _client_side_script(file_path: str) -> str:
    """Return bash + PowerShell scripts for client-side schema extraction."""
    fp = file_path.replace('"', '\\"')
    out = re.sub(r"\.(json|JSON)$", "_schema.json", fp)
    if out == fp:
        out = fp + ".schema.json"

    bash_script = f'''#!/usr/bin/env bash
set -euo pipefail
INPUT="{fp}"
OUTPUT="{out}"
if [ ! -f "$INPUT" ]; then echo "ERROR: file not found: $INPUT"; exit 1; fi
python3 -c {repr(_CLIENT_SCHEMA_SCRIPT)} "$INPUT" "$OUTPUT"'''

    ps_script = f'''$InputFile = "{fp}"
$OutputFile = "{out}"
if (-not (Test-Path $InputFile)) {{ Write-Error "File not found: $InputFile"; exit 1 }}
$script = @'
{_CLIENT_SCHEMA_SCRIPT}
'@
$tempScript = [System.IO.Path]::GetTempFileName() + ".py"
[System.IO.File]::WriteAllText($tempScript, $script)
python $tempScript $InputFile $OutputFile
Remove-Item $tempScript
'''

    return json.dumps({
        "instruction": (
            f"Run ONE of the scripts below on the client machine to extract "
            f"the schema locally. Output will be saved to: {out}"
        ),
        "powershell": ps_script,
        "bash": bash_script,
        "requires": "Python 3 (no extra packages needed)",
        "output_file": out,
    }, indent=2)


def register(mcp):
    @mcp.tool()
    def extract_json_schema(file_path: str) -> str:
        """Extract a detailed JSON schema from a JSON file on the client machine.

        DO NOT read the file. Just pass the absolute file path.
        The tool returns a script to run on the client that extracts the schema.
        This works for any file size and correctly detects base64 image data.

        Detects: number_as_string, base64, uuid, date-time, date, email, uri,
        integer_as_string, empty_string, and more.

        Args:
            file_path: Absolute path to a JSON file on the CLIENT machine.
                Example: "C:/Users/me/request.json"

        Returns:
            Instructions and a script (PowerShell + bash) to run on the client.
            The script extracts the schema and saves it next to the original file.
        """
        if not file_path or not file_path.strip():
            return json.dumps({"error": "file_path is required."}, indent=2)
        return _client_side_script(file_path.strip())
