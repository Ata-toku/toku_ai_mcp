import json


def register(mcp):
    @mcp.tool()
    def image_to_base64(
        image_path: str,
        output_path: str = "",
    ) -> str:
        """Get a ready-to-run script that converts an image file to base64 on the CLIENT machine.

        This tool does NOT process images on the server. It returns bash and
        PowerShell scripts that the agent must execute locally via run_in_terminal.

        WORKFLOW:
        1. Call this tool with the image path on the client machine.
        2. The tool returns scripts for bash and PowerShell.
        3. Run the appropriate script in the terminal on the client machine.
        4. The script outputs base64 to stdout or saves to a file.

        Args:
            image_path: Absolute path to the image file on the CLIENT machine.
                Example: "C:/Users/me/photo.png" or "/home/me/photo.png"
            output_path: Optional file path to save the base64 output.
                If empty, base64 is printed to stdout.

        Returns:
            Instructions and scripts (bash + PowerShell) to run on the client.
        """
        img = image_path.replace('"', '\\"')
        out = output_path.replace('"', '\\"') if output_path else ""

        if out:
            bash_script = f'''#!/usr/bin/env bash
# Image → Base64  (saves to file)
set -euo pipefail
INPUT="{img}"
OUTPUT="{out}"
if [ ! -f "$INPUT" ]; then echo "ERROR: file not found: $INPUT"; exit 1; fi
base64 -w 0 "$INPUT" > "$OUTPUT"
MIME=$(file --mime-type -b "$INPUT")
SIZE=$(stat -c%s "$INPUT" 2>/dev/null || stat -f%z "$INPUT")
echo "Done. MIME=$MIME  Size=$SIZE bytes  Output=$OUTPUT"'''

            ps_script = f'''# Image → Base64  (saves to file)
$ImagePath = "{img}"
$OutputPath = "{out}"
if (-not (Test-Path $ImagePath)) {{ Write-Error "File not found: $ImagePath"; exit 1 }}
$bytes = [System.IO.File]::ReadAllBytes($ImagePath)
$b64 = [System.Convert]::ToBase64String($bytes)
[System.IO.File]::WriteAllText($OutputPath, $b64)
$ext = [System.IO.Path]::GetExtension($ImagePath).ToLower()
Write-Host "Done. Extension=$ext  Size=$($bytes.Length) bytes  Output=$OutputPath"'''
        else:
            bash_script = f'''#!/usr/bin/env bash
# Image → Base64  (stdout)
set -euo pipefail
INPUT="{img}"
if [ ! -f "$INPUT" ]; then echo "ERROR: file not found: $INPUT"; exit 1; fi
base64 -w 0 "$INPUT"'''

            ps_script = f'''# Image → Base64  (stdout)
$ImagePath = "{img}"
if (-not (Test-Path $ImagePath)) {{ Write-Error "File not found: $ImagePath"; exit 1 }}
$bytes = [System.IO.File]::ReadAllBytes($ImagePath)
[System.Convert]::ToBase64String($bytes)'''

        return json.dumps({
            "instruction": (
                "Run ONE of the scripts below in the client terminal to convert "
                f"'{image_path}' to base64. Use the PowerShell script on Windows "
                "or the bash script on Linux/macOS."
            ),
            "powershell": ps_script,
            "bash": bash_script,
        }, indent=2)
