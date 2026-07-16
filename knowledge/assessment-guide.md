# Client-Side Retinal Assessment

Use this workflow for requests to run an assessment, retinal screening, model
wrapper analysis, CLAIR, BioAge, or a batch of retinal images.

## Execution Boundary

The MCP server prepares files only. It must never read client-local images,
encode images, call a model endpoint, or save assessment results. Those actions
must happen on the MCP client's machine through the runner returned by
`prepare_assessment`.

## Workflow

1. Determine the client OS as `windows`, `linux`, or `macos` when it is not
   already known.
2. Call `collect_assessment_intake` immediately after `start_retinal_assessment`
   to attempt the native MCP elicitation form. Let the SDK negotiate whether the
   client actually supports elicitation; do not guess. Only if it returns status
   `elicitation_unavailable` should you fall back to the normal one-question-at-a-time
   chat flow below. Ask exactly one next missing field at a time. Do not print a
   checklist. Do not ask for image paths or image/Base64 format before
   preparation.
3. When the endpoint is missing, call `list_assessment_endpoints` and ask the user to
   select one returned `endpoint_name`. Present only those exact names. Do not
   invent choices based on assessment intent, such as `Retinal screening`,
   `CLAIR`, or `BioAge`: these are not endpoint names. Pass the selected name
   unchanged to `prepare_assessment`.
4. Call `prepare_assessment` without `image_paths` unless the user already
   supplied paths. The runner scans only the directory containing
   `assessment-request.json`, ignores results and virtual-environment folders,
   and uses supported image files (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`,
   `.bmp`) or Base64 image files (`.b64`, `.base64`). It detects the contents
   locally; do not ask the user which format they have. Ask for paths only when
   the runner reports fewer than two usable files.
5. In the chat fallback only (elicitation unavailable), ask any remaining
   patient fields one at a time. Never ask for the patient's first or last
   name: `FirstName` and `LastName` are auto-generated random placeholder
   strings for the model wrapper API call, not user-supplied fields. Call
   `get_assessment_intake_schema` only for the next constrained field when its
   exact options or format are not already known. Never replace a constrained
   choice with free text. The required controls are:

   | Field | Choices | Follow-up |
   |---|---|---|
   | `DiabetesStatus` | `Yes`, `No` | None |
   | `SmokingStatus` | `Yes`, `No` | None |
   | `camera` | `NW400`, `NW500`, `OPTOS`, `Other` | Ask for a camera name only when `Other` is selected. Store the user-provided name in `camera`. |

   The DOB prompt must visibly state `YYYY/MM/DD` and show `1985/06/02` as its
   example. Do not ask free-text questions for diabetes or smoking status. Do
   not show a free-text camera input unless the user selects `Other`.
6. Confirm all values with the user. Patient information is sensitive and must
   not be inferred from unrelated conversation context.
7. Call `prepare_assessment` with the OS, endpoint name, and a JSON object using
   this shape. Omit `FirstName` and `LastName`; the server fills them with
   random placeholder values automatically:

```json
{
  "Sex": "M",
  "camera": "OPTOS",
  "DOB": "1990/04/20",
  "DiabetesStatus": "No",
  "SmokingStatus": "No",
   "image_paths": []
}
```

7. On the client, write every returned file into one temporary or working
   directory and execute the returned command exactly from that directory.
   Windows receives a PowerShell runner and requires PowerShell 5.1 or newer.
   Linux and macOS receive a Bash launcher plus a Python 3 runner; both Bash
   and Python 3.10 or newer must be available. The runners use no third-party
   packages: Windows validates its required built-in cmdlets, and Linux/macOS
   validate the `python3` command and version. Each runner repeats request
   validation on the client before it reads images or makes an API call.
8. Read the `response_path` printed by the runner, explain the result, and keep
   the request/response files at the paths selected by the client.

## Validation

- `Sex` is `M` or `F`.
- `DOB` uses `YYYY/MM/DD`.
- Diabetes and smoking values are `Yes` or `No`.
- When supplied, image paths are non-empty. Otherwise, the client runner must
   discover at least two usable images beside `assessment-request.json`.
- Never place Base64 image data in an MCP tool call.
- Never send a model API request from the MCP server host.

Use structured question UI when the client provides it. Otherwise use ordinary
chat questions. Use the client's command execution facility when available; if
it is unavailable, return the prepared files and command to the user without
claiming the assessment ran.