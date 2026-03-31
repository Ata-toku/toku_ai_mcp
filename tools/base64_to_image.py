import json


def register(mcp):
    @mcp.tool()
    def base64_to_image(
        base64_path: str,
        output_path: str,
        format: str = "png",
    ) -> str:
        """Get a ready-to-run script that decodes base64 back to an image file on the CLIENT machine.

        Optionally converts between formats (PNG ↔ JPEG). This tool does NOT
        process images on the server. It returns bash and PowerShell scripts
        that the agent must execute locally via run_in_terminal.

        WORKFLOW:
        1. Call this tool with the base64 file path and desired output path.
        2. The tool returns scripts for bash and PowerShell.
        3. Run the appropriate script in the terminal on the client machine.
        4. The script decodes base64 and saves the image file.

        Args:
            base64_path: Path to a text file containing base64-encoded image data
                on the CLIENT machine. Can also be "STDIN" if piping.
            output_path: Where to save the decoded image on the CLIENT machine.
                Example: "C:/Users/me/output.jpeg" or "/tmp/output.png"
            format: Target format - "png", "jpeg", or "same" to keep original
                (default: "png"). Only matters if you want format conversion.

        Returns:
            Instructions and scripts (bash + PowerShell) to run on the client.
        """
        b64p = base64_path.replace('"', '\\"')
        outp = output_path.replace('"', '\\"')
        fmt = format.lower().strip()

        if fmt in ("jpg", "jpeg"):
            convert_note = "Output will be JPEG."
            py_convert = (
                f'python -c "'
                f"import base64,sys; from PIL import Image; import io; "
                f"d=base64.b64decode(open(r'{b64p}').read().strip()); "
                f"img=Image.open(io.BytesIO(d)); "
                f"img=img.convert('RGB') if img.mode in ('RGBA','P') else img; "
                f"img.save(r'{outp}','JPEG',quality=95)"
                f'"'
            )
            bash_script = f'''#!/usr/bin/env bash
# Base64 → Image  (with JPEG conversion)
set -euo pipefail
B64FILE="{b64p}"
OUTPUT="{outp}"
if [ ! -f "$B64FILE" ]; then echo "ERROR: file not found: $B64FILE"; exit 1; fi
# Requires Python + Pillow for format conversion
{py_convert}
echo "Done. Saved JPEG to $OUTPUT"'''

            ps_script = f'''# Base64 → Image  (with JPEG conversion)
$B64File = "{b64p}"
$Output = "{outp}"
if (-not (Test-Path $B64File)) {{ Write-Error "File not found: $B64File"; exit 1 }}
# Requires Python + Pillow for format conversion
python -c "import base64,sys; from PIL import Image; import io; d=base64.b64decode(open(r'$B64File').read().strip()); img=Image.open(io.BytesIO(d)); img=img.convert('RGB') if img.mode in ('RGBA','P') else img; img.save(r'$Output','JPEG',quality=95)"
Write-Host "Done. Saved JPEG to $Output"'''

        elif fmt == "png":
            convert_note = "Output will be PNG."
            py_convert = (
                f'python -c "'
                f"import base64,sys; from PIL import Image; import io; "
                f"d=base64.b64decode(open(r'{b64p}').read().strip()); "
                f"img=Image.open(io.BytesIO(d)); "
                f"img.save(r'{outp}','PNG')"
                f'"'
            )
            bash_script = f'''#!/usr/bin/env bash
# Base64 → Image  (with PNG conversion)
set -euo pipefail
B64FILE="{b64p}"
OUTPUT="{outp}"
if [ ! -f "$B64FILE" ]; then echo "ERROR: file not found: $B64FILE"; exit 1; fi
{py_convert}
echo "Done. Saved PNG to $OUTPUT"'''

            ps_script = f'''# Base64 → Image  (with PNG conversion)
$B64File = "{b64p}"
$Output = "{outp}"
if (-not (Test-Path $B64File)) {{ Write-Error "File not found: $B64File"; exit 1 }}
python -c "import base64,sys; from PIL import Image; import io; d=base64.b64decode(open(r'$B64File').read().strip()); img=Image.open(io.BytesIO(d)); img.save(r'$Output','PNG')"
Write-Host "Done. Saved PNG to $Output"'''

        else:  # "same" — direct decode, no conversion
            convert_note = "Output keeps original format (no conversion)."
            bash_script = f'''#!/usr/bin/env bash
# Base64 → Image  (direct decode, no format conversion)
set -euo pipefail
B64FILE="{b64p}"
OUTPUT="{outp}"
if [ ! -f "$B64FILE" ]; then echo "ERROR: file not found: $B64FILE"; exit 1; fi
base64 -d "$B64FILE" > "$OUTPUT"
echo "Done. Saved to $OUTPUT  Size=$(stat -c%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT") bytes"'''

            ps_script = f'''# Base64 → Image  (direct decode, no format conversion)
$B64File = "{b64p}"
$Output = "{outp}"
if (-not (Test-Path $B64File)) {{ Write-Error "File not found: $B64File"; exit 1 }}
$b64 = [System.IO.File]::ReadAllText($B64File).Trim()
$bytes = [System.Convert]::FromBase64String($b64)
[System.IO.File]::WriteAllBytes($Output, $bytes)
Write-Host "Done. Saved to $Output  Size=$($bytes.Length) bytes"'''

        return json.dumps({
            "instruction": (
                f"Run ONE of the scripts below in the client terminal. {convert_note} "
                f"Use PowerShell on Windows or bash on Linux/macOS.\n\n"
                f"For INLINE base64 (not from file), replace the file-read "
                f"with a string variable containing the base64 data."
            ),
            "powershell": ps_script,
            "bash": bash_script,
            "requires": "Python + Pillow (pip install Pillow)" if fmt != "same" else "none",
        }, indent=2)
