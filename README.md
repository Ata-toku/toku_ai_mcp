# TokuEyes AI MCP Server

A streamable HTTP Model Context Protocol (MCP) server for TokuEyes AI systems,
models, infrastructure knowledge, retinal assessment preparation, image and JSON
utilities, and vulnerability intake workflows.

The server implements all three standard MCP primitives:

| Primitive | Count | Purpose |
|---|---:|---|
| Tools | 12 | Search knowledge and prepare client-side operations |
| Resources | 3 static + 1 template | Expose documents, endpoints, and operating guides |
| Prompts | 2 | Guide grounded answers and retinal assessments |

The MCP endpoint is `/mcp`. Direct Python execution listens on port `8000`; the
included Docker Compose configuration publishes it on host port `8093`.

## Design Principles

- **Grounded answers:** system and model answers come from files under
  `knowledge/`; clients should cite the returned source paths and not guess.
- **Live knowledge:** supported knowledge files are discovered recursively and
  reindexed automatically when files are added, changed, or removed.
- **Client-side assessment execution:** the server never reads client retinal
  images and never calls the model wrapper API. It prepares validated files and
  an exact command for execution on the client's machine.
- **Cross-platform artifacts:** client-side operations return PowerShell for
  Windows and Bash or Python alternatives for Linux and macOS.
- **Standard MCP discovery:** capabilities are available through `tools/list`,
  `resources/list`, `resources/templates/list`, and `prompts/list`.

## Requirements

- Python 3.10 or newer
- `mcp[cli]>=1.26.0,<2`
- `python-docx>=1.1.2`
- `requests>=2.31.0`
- Docker and Docker Compose, if running the containerized server

Some generated client scripts have additional local requirements. These are
listed under the relevant tool below.

## Installation and Run

### Local Python

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python server.py
```

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python server.py
```

The MCP endpoint is:

```text
http://localhost:8000/mcp
```

### Docker Compose

```bash
docker compose up --build
```

The published MCP endpoint is:

```text
http://localhost:8093/mcp
```

The image runs as a non-root user. The Docker build copies the server, tools,
knowledge corpus, and assessment runner templates into the image.

## MCP Capability Summary

### Resources

| URI | Type | Provides |
|---|---|---|
| `toku://knowledge/catalog` | Static JSON | Catalog of every indexed knowledge document |
| `toku://knowledge/{document}` | URI template | Complete content of one catalog document |
| `toku://assessment/guide` | Static Markdown | OS-agnostic client-side assessment procedure |
| `toku://assessment/endpoints` | Static JSON | Configured model wrapper endpoints |

### Prompts

| Name | Provides |
|---|---|
| `answer_from_knowledge` | A grounded question-answering prompt with ranked source context |
| `run_assessment` | The assessment guide, known request details, OS context, and endpoint choices |

### Tools

| Name | Execution | Provides |
|---|---|---|
| `search_knowledge` | Server | Ranked source passages from the live knowledge corpus |
| `refresh_knowledge_index` | Server | Forced rebuild and indexed document count |
| `start_retinal_assessment` | Server | Required first tool; returns the exact first endpoint question and literal options |
| `list_assessment_endpoints` | Server | Exact configured endpoint names for assessment selection |
| `collect_assessment_intake` | Server/client interactive form | Native MCP elicitation for patient metadata, endpoint, and image paths |
| `get_assessment_intake_schema` | Server | Exact patient-intake questions, option values, and DOB format |
| `prepare_assessment` | Preparation on server; execution on client | Validated request, OS-specific runner, and exact command |
| `standalone_image_to_base64` | Client | PowerShell and Bash image-to-Base64 scripts |
| `standalone_base64_to_image` | Client | PowerShell and Bash Base64 decoding/conversion scripts |
| `extract_json_schema` | Client | Scripts that infer a descriptive schema from local JSON |
| `fetch_vulnerability_context` | Server | NVD/CVE context and an AI analysis prompt |
| `fill_vulnerability_form` | Server preparation; save on client | Completed FM-004 Word document encoded in save scripts |

## Resource Reference

### `toku://knowledge/catalog`

Returns an `application/json` catalog of the currently indexed files. Each entry
contains:

- `title`: title inferred from the first Markdown H1 or the filename
- `path`: path relative to `knowledge/`
- `uri`: encoded URI that can be passed directly to `resources/read`
- `media_type`: detected MIME type

Example shape:

```json
{
  "documents": [
    {
      "title": "AI Infrastructure Architecture",
      "path": "AI_INFRASTRUCTURE_ARCHITECTURE.md",
      "uri": "toku://knowledge/AI_INFRASTRUCTURE_ARCHITECTURE.md",
      "media_type": "text/markdown"
    }
  ]
}
```

Use this resource when a client needs to discover authoritative files or select
a complete document rather than a ranked excerpt.

### `toku://knowledge/{document}`

A resource template that returns one complete knowledge document. The
`document` value is the URL-encoded relative path emitted by the catalog.
Nested paths are encoded so the URI remains valid.

Example:

```text
toku://knowledge/templates%2Fmodelwrapper_request_schema.json
```

Unknown document paths return an MCP resource error. Clients should obtain URIs
from the catalog instead of constructing them manually.

### `toku://assessment/guide`

Returns the authoritative Markdown workflow for retinal assessments. It covers:

- OS detection or collection
- endpoint selection
- patient and image-path collection
- request validation
- confirmation of sensitive patient data
- use of `prepare_assessment`
- client-local execution and result reading
- the prohibition on sending image bytes through MCP

This resource does not run an assessment.

### `toku://assessment/endpoints`

Returns the contents of `knowledge/templates/endpoints.json`. Each named entry
contains its `model_wrapper_endpoint` and may contain descriptive connection
requirements or host details.

Update that JSON file to add, remove, or change assessment targets without
changing Python code.

## Prompt Reference

### `answer_from_knowledge`

Prepares a grounded response for questions about TokuEyes systems, AI models,
infrastructure, repositories, deployment, testing, or other indexed material.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `question` | Yes | Natural-language question to answer |

The prompt internally searches for up to five ranked passages and instructs the
model to:

- use only the supplied context
- cite factual sections using their source paths
- state what information is missing when context is insufficient
- avoid unsupported inference

Use the prompt when the desired outcome is a final natural-language answer. Use
`search_knowledge` directly when an application needs structured search results.

### `run_assessment`

Prepares an interactive, client-side retinal assessment workflow.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `operating_system` | No | Known client OS; normally `windows`, `linux`, or `macos` |
| `request_details` | No | Patient details, image paths, or selections already supplied by the user |

The prompt combines:

- the assessment guide
- known OS information
- known request details
- the latest configured endpoint list

It guides the client to collect only missing information, confirm sensitive
values, call `prepare_assessment`, write the returned files locally, and execute
the exact returned command. It does not itself read images or call the API.

## Tool Reference

### `search_knowledge`

Searches all supported files under `knowledge/` and returns ranked passages.
The index checks the filesystem before each operation and rebuilds automatically
when its path, modified-time, and size fingerprint changes.

Arguments:

| Argument | Required | Default | Description |
|---|---:|---:|---|
| `query` | Yes | - | Natural-language search query |
| `limit` | No | `5` | Number of matches; constrained to `1` through `10` |

Each match contains:

- `source`: relative source path
- `title`: source title
- `heading`: Markdown section or inferred document title
- `score`: relevance score
- `content`: grounded source passage

If nothing matches, the tool returns an empty `matches` array and an explicit
message. The tool does not generate an answer by itself.

### `refresh_knowledge_index`

Forces a complete knowledge index rebuild even when the filesystem fingerprint
has not changed.

Arguments: none.

Returns:

```json
{
  "refreshed": true,
  "document_count": 9
}
```

Normal edits do not require this tool because refresh is automatic. It is useful
after unusual filesystem operations where timestamps or file sizes were
preserved.

### `list_assessment_endpoints`

Returns the exact endpoint names available to `prepare_assessment` in a
structured JSON response. Call this tool before asking an assessment user to
choose a target.

Arguments: none.

Each returned item contains `endpoint_name`, `endpoint_url`, and
`requirements`. Present only the literal `endpoint_name` values as choices and
pass the selected value unchanged to `prepare_assessment`. Do not invent labels
such as `Retinal screening`, `CLAIR`, or `BioAge`; they are assessment intents,
not endpoint names.

### `get_assessment_intake_schema`

Returns the authoritative machine-readable patient-intake schema. Call it before
asking for missing patient metadata, then render every `single_select` field as
buttons or a selection list using the returned `label` and `value` pairs.

Arguments: none.

The schema includes the exact values required by the API:

- Sex: `Male` -> `M`; `Female` -> `F`
- Camera: `NW400`, `NW500`, `OPTOS`, or `Other`; only `Other` permits free text
- DOB: input format and example `YYYY/MM/DD`, for example `1985/06/02`
- Diabetes status: `Yes` or `No`
- Smoking status: `Yes` or `No`

`prepare_assessment` safely normalizes common unambiguous answers such as
`Male`, `nw400`, `1985-06-02`, and `Never smoked`. Its `normalizations` response
field records every conversion. This is a fallback, not a replacement for
rendering the structured intake schema.

### `collect_assessment_intake`

This optional tool uses standard MCP elicitation to open one interactive form in
clients that explicitly advertise elicitation support. The form provides selectable controls for
sex, camera, diabetes status, and smoking status; validates DOB as `YYYY/MM/DD`;
and collects an endpoint. It deliberately does not ask for image paths or image
format: the client runner discovers and classifies files locally.

On acceptance, it returns an `endpoint_name` and canonical `request` object for
`prepare_assessment`. The tool never accesses images or calls the model API.
When elicitation support is not explicitly advertised, do not call this tool.
Ask exactly one next missing field in chat instead, and call
`get_assessment_intake_schema` only for the next constrained question.

### Automatic Client Image Discovery

When `request_json.image_paths` is absent or empty, the client runner scans only
the directory that contains `assessment-request.json`. It uses supported image
files (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`) and Base64 image files
(`.b64`, `.base64`), validates their bytes locally, and ignores `results`, Git,
and virtual-environment folders. It needs at least two usable files. Ask the
user for paths only if that local check fails; never ask whether files are image
or Base64 first.

### `prepare_assessment`

Validates assessment metadata and returns a complete client-side execution
package. It does not verify client file existence, read image contents, encode
images, call an endpoint, or save results on the server.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `operating_system` | Yes | Exactly `windows`, `linux`, or `macos`, case-insensitive |
| `endpoint_name` | Yes | Key from `toku://assessment/endpoints` |
| `request_json` | Yes | JSON string containing patient fields and client-local image paths |

Required `request_json` shape:

```json
{
  "Sex": "F",
  "camera": "OPTOS",
  "DOB": "1990/04/20",
  "DiabetesStatus": "No",
  "SmokingStatus": "No",
  "image_paths": [
    "C:/assessment/right.jpg",
    "C:/assessment/left.jpg"
  ]
}
```

`FirstName` and `LastName` are never collected from the user. `prepare_assessment`
auto-generates random placeholder strings for both before calling the model
wrapper API; supplying them explicitly in `request_json` still works but is not required.

Validation rules:

- all patient fields must be non-empty
- `Sex` must be `M` or `F`
- `DOB` must match `YYYY/MM/DD`
- diabetes and smoking status must be `Yes` or `No`
- at least two non-empty image paths are required
- the endpoint must exist and use `http://` or `https://`

When collecting missing fields through a client with structured-question
support, present `Yes` and `No` choices for both diabetes and smoking status.
Present exactly four camera choices: `NW400`, `NW500`, `OPTOS`, and `Other`.
Request a free-text camera name only after the user selects `Other`.

The response contains:

- `execution_location`: always `MCP client machine only`
- `server_called_model_api`: always `false`
- `files`: an OS-specific runner and `assessment-request.json`
- `command`: exact command to run from the directory containing both files
- `next_steps`: write, execute, and read-result instructions

Windows receives `run_assessment.ps1` and requires PowerShell 5.1 or newer.
It validates the availability of required built-in cmdlets and uses no
third-party PowerShell modules. Linux and macOS receive `run_assessment.sh` plus
the standard-library-only `run_assessment.py`; they require Bash and Python 3.10
or newer, with no third-party Python packages. The POSIX launcher checks that
`python3` exists and meets the version requirement before starting the shared
runner. Each runner revalidates all patient fields, endpoint URL, and image
paths locally before it reads images, constructs the API payload, performs the
POST, and saves timestamped request and response JSON files under `results/`.

### `standalone_image_to_base64`

Returns scripts to convert a client-local image to Base64. No image bytes are
sent to or processed by the MCP server.

Arguments:

| Argument | Required | Default | Description |
|---|---:|---:|---|
| `image_path` | Yes | - | Absolute client-local image path |
| `output_path` | No | empty | Destination text file; empty prints Base64 to stdout |

Returns JSON containing `instruction`, `powershell`, and `bash`. The client runs
one script appropriate to its OS. The Bash script uses standard `base64`,
`file`, and `stat` utilities; PowerShell uses .NET APIs.

### `standalone_base64_to_image`

Returns scripts to decode a Base64 text file into an image on the client.
Optionally converts the decoded image to PNG or JPEG.

Arguments:

| Argument | Required | Default | Description |
|---|---:|---:|---|
| `base64_path` | Yes | - | Client-local text file containing Base64 data |
| `output_path` | Yes | - | Client-local destination image path |
| `format` | No | `png` | `png`, `jpeg`/`jpg`, or `same` |

Return fields are `instruction`, `powershell`, `bash`, and `requires`.

- `same` performs direct decoding and requires no Python package.
- PNG or JPEG conversion requires Python and Pillow on the client:
  `pip install Pillow`.

The output extension alone does not control conversion; select the matching
`format` argument.

### `extract_json_schema`

Returns scripts that inspect a client-local JSON file and save a descriptive
schema beside it. The source JSON is never uploaded to the server, making the
flow suitable for large files and payloads containing Base64 image data.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `file_path` | Yes | Absolute client-local JSON path |

The generated output name is `<name>_schema.json` for `.json` inputs or
`<name>.schema.json` otherwise. Detection includes:

- objects, arrays, nulls, booleans, integers, and numbers
- numeric and integer strings
- Base64 strings and approximate decoded size
- UUIDs
- dates and date-times
- email addresses and HTTP(S) URIs
- empty strings

Returns `instruction`, `powershell`, `bash`, `requires`, and `output_file`.
Only Python 3 is required on the client; no third-party package is needed.

### `fetch_vulnerability_context`

Starts the FM-004 vulnerability intake workflow. The server fetches CVE metadata
from NVD and supplementary CVE.org content, then prepares a focused AI analysis
prompt.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `cve_id` | Yes | CVE identifier such as `CVE-2023-6597` |
| `source_report` | Yes | Finding source, such as Defender, Vanta, pen test, or Dependabot |

A successful result has status `analysis_needed` and provides:

- a CVE summary including CVSS, publication date, and description
- `cve_context_json` for the next tool call
- `analysis_prompt` to run with the client model in chat
- ordered instructions

The client must keep `cve_context_json` in memory, run `analysis_prompt`, parse
the model's JSON response, and pass both JSON strings to
`fill_vulnerability_form`. API lookup failures return status `error` with a
message.

This is the one workflow that performs external server-side network requests.
It does not access client-local files.

### `fill_vulnerability_form`

Completes the FM-004 Word template using CVE context plus the structured AI
analysis from the previous step.

Arguments:

| Argument | Required | Description |
|---|---:|---|
| `cve_context_json` | Yes | Exact context string returned by `fetch_vulnerability_context` |
| `ai_analysis_json` | Yes | JSON block produced by the supplied analysis prompt |

The server builds the `.docx` in memory and returns:

- `status`
- `cve_id`
- `filename`
- `powershell_script`
- `bash_script`
- `instructions`

The returned script decodes the document on the client and saves it in the
current working directory. The server does not directly write the completed
form to the client filesystem. Invalid JSON, document-generation failures, or a
missing Word template return an error string.

## Complete Assessment Workflow

1. Call `start_retinal_assessment`. Ask its exact endpoint question using only its literal options. Do not call `list_assessment_endpoints`, `standalone_image_to_base64`, or `standalone_base64_to_image`.
2. Ask only the next missing field in chat. Call `collect_assessment_intake` only when the client explicitly advertises elicitation support.
3. Use `list_assessment_endpoints` only outside the normal assessment-start workflow.
4. Use `get_assessment_intake_schema` only for the next constrained question when needed.
5. Call `prepare_assessment` with the OS, endpoint name, and request JSON. Omit image paths unless the user already gave them.
6. Write both returned files into one client-local working directory.
7. Run the returned command exactly from that directory.
8. Read the printed `response_path` and summarize the result.

`standalone_image_to_base64` and `standalone_base64_to_image` are standalone conversion utilities.
They are not part of the assessment workflow because the client runner detects
and encodes image or Base64 files itself.

Do not put Base64 image data in MCP requests. Patient metadata is passed to
`prepare_assessment`, so MCP transport and server access controls must be
appropriate for sensitive information.

## Complete Vulnerability Workflow

1. Collect `cve_id` and `source_report`.
2. Call `fetch_vulnerability_context`.
3. Run its `analysis_prompt` with the client model.
4. Keep both JSON payloads in memory; do not create intermediate files.
5. Call `fill_vulnerability_form`.
6. Execute the returned PowerShell or Bash save script on the client.
7. Confirm the generated `.docx` path.

## Knowledge Index

### Supported Files

The index recursively includes:

- `.md`
- `.json`
- `.txt`
- `.yaml`
- `.yml`

Other file types, including the Word template, are not indexed as knowledge.
JSON is parsed and normalized before indexing, so invalid JSON causes index
refresh to fail and should be corrected.

### Indexing and Ranking

Documents are split primarily at Markdown headings and then into chunks of up
to 4,000 characters. Search tokenizes paths, headings, and content and ranks
matches using term frequency weighted by inverse chunk frequency. The index is
in memory and guarded for concurrent access.

The automatic fingerprint includes each supported file's relative path,
modified timestamp, and size. A corpus change triggers a complete rebuild on
the next catalog, document, or search operation.

### Updating Knowledge

1. Add, edit, move, or remove supported files under `knowledge/`.
2. Use the server normally; the next knowledge operation detects the change.
3. Optionally call `refresh_knowledge_index` to force immediate rebuilding.
4. Read `toku://knowledge/catalog` to verify discovery.
5. Test a representative query with `search_knowledge`.

No Python code change or server restart is normally required.

## Configuration

### Assessment Endpoints

Edit `knowledge/templates/endpoints.json`. The top-level key is the
`endpoint_name` accepted by `prepare_assessment`.

```json
{
  "example-environment": {
    "model_wrapper_endpoint": "https://model-wrapper.example/api/extended/analyse",
    "name": "example-environment",
    "requirements": [
      "Requires network access to the model wrapper service"
    ]
  }
}
```

Do not store credentials in this file. Use authenticated network controls or an
appropriate secret-management mechanism if endpoint authentication is added.

### Server Binding

`server.py` configures FastMCP to bind to `0.0.0.0:8000` using streamable HTTP.
Docker Compose maps host port `8093` to container port `8000`.

## Project Structure

```text
server.py                         FastMCP server and global instructions
tools/__init__.py                 Capability registration
tools/knowledge_base.py           Live index, resources, search tool, QA prompt
tools/run_assessment.py           Assessment resources, prompt, preparation tool
tools/image_to_base64.py          Client-side image encoding artifact generator
tools/base64_to_image.py          Client-side image decoding artifact generator
tools/extract_json_schema.py      Client-side JSON schema artifact generator
tools/vulnerability_form.py       CVE lookup and FM-004 document generation
knowledge/                        Mutable knowledge corpus
knowledge/assessment-guide.md     Authoritative assessment procedure
knowledge/templates/endpoints.json Assessment endpoint configuration
scripts/run_assessment.ps1        Windows client assessment runner template
scripts/run_assessment.py         Linux/macOS client assessment runner template
test_mcp.py                       Registration and knowledge-index unit tests
test_call.py                      Live streamable HTTP capability smoke test
Dockerfile                        Non-root production image
docker-compose.yml                Local container orchestration
```

## Testing

Run compilation and unit tests:

```powershell
python -m compileall -q server.py tools scripts test_mcp.py test_call.py
python -m unittest discover -v
```

The unit suite verifies:

- expected tools, resources, resource templates, and prompts are registered
- the knowledge catalog emits readable document URIs
- the index refreshes after a source file changes

Run the live protocol smoke test in a second terminal after starting the server:

```powershell
python server.py
```

```powershell
python test_call.py
```

The smoke test initializes an MCP session and lists tools, resources, and
prompts over streamable HTTP.

Validate the container:

```powershell
docker build -t toku-ai-mcp:validation .
docker run --rm toku-ai-mcp:validation python -c "import server; print('server import ok')"
```

## Security and Operational Notes

- Run the service only on trusted networks unless authentication, authorization,
  and TLS termination are provided by a gateway or reverse proxy.
- Treat assessment patient fields and generated results as sensitive data.
- The server does not receive retinal image bytes during assessment preparation.
- Generated scripts should be reviewed or executed only after explicit user
  intent is established.
- Endpoint definitions are configuration, not a place for passwords or tokens.
- CVE lookup tools require outbound access to NVD and CVE.org.
- The vulnerability form embeds the generated document as Base64 in the returned
  save script; clients must account for the resulting response size.
- Keep the Python base image and dependencies patched and scan built images in
  CI, since upstream image findings can change independently of this repository.

## Troubleshooting

### A knowledge file is missing

Confirm that it is under `knowledge/` and has a supported extension. Call
`refresh_knowledge_index`, then inspect `toku://knowledge/catalog`.

### Search returns no matches

Use concrete domain terms present in the source files. Read the catalog to check
which documents are available. The search intentionally returns no answer when
there is no grounded match.

### Assessment preparation rejects the request

Check the exact field names and casing, `YYYY/MM/DD` date format, allowed enum
values, at least two image paths, and a valid configured endpoint name.

### The prepared assessment command cannot read an image

The image paths are interpreted on the MCP client's machine, not the server or
container. Use absolute paths valid for that operating system and ensure the
client process has read permission.

### Image conversion fails

For PNG/JPEG conversion in `standalone_base64_to_image`, install Pillow on the client. Use
`format="same"` when only direct decoding is needed.

### Vulnerability lookup fails

Verify the CVE identifier, outbound DNS/HTTPS connectivity, and availability of
NVD/CVE.org. The tool returns an error status when metadata cannot be obtained.
