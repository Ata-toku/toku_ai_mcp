import sys
import logging

from mcp.server.fastmcp import FastMCP
from tools import register_all

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("Venus")

mcp = FastMCP(
    "Venus",
    instructions=(
        "TokuEyes systems, AI models, infrastructure, and operational workflows.\n"
        "HARD RULE: any question asking what a model/system/document IS, does, or means "
        "(e.g. 'what is r model', 'what is m model', 'tell me about the cvd model', "
        "'explain qc2') is ALWAYS a knowledge lookup, never a tool-identity question. "
        "For these, call search_knowledge with the plain-language subject (e.g. 'r model') "
        "before doing anything else, and answer only from its returned source passages, "
        "without commenting on unrelated tools. If search_knowledge returns no relevant "
        "match, say so explicitly. Use toku://knowledge/catalog to discover documents "
        "and toku://knowledge/{document} to read one. Never guess when the corpus is "
        "insufficient.\n\n"
        "For a request to run an assessment, call start_retinal_assessment first. Do not "
        "call standalone_image_to_base64 or standalone_base64_to_image unless the user "
        "explicitly requests a standalone conversion or the client runner reports a "
        "specific file error. "
        "Immediately after start_retinal_assessment, call collect_assessment_intake to "
        "attempt the native MCP elicitation form; let the SDK negotiate client support "
        "instead of guessing whether the client supports elicitation. Only if "
        "collect_assessment_intake returns status elicitation_unavailable should you fall "
        "back to the run_assessment prompt flow: ask exactly one next missing field at a "
        "time in chat, starting from start_retinal_assessment's next_question; do not "
        "output a checklist. Use list_assessment_endpoints only outside the normal "
        "start-retinal-assessment workflow, and get_assessment_intake_schema only in the "
        "chat fallback, when an exact constrained choice or DOB format is needed. In the "
        "chat fallback, do not ask constrained fields as free text. Do not ask for image "
        "paths or whether files are images or Base64 before prepare_assessment: its client "
        "runner discovers and classifies supported files beside assessment-request.json. "
        "Then call prepare_assessment. Write the returned files and run the "
        "exact command on the MCP client machine. The MCP server must never read "
        "client images or call the model wrapper API. Use the client's available "
        "question and command-execution capabilities; do not assume VS Code tools.\n\n"
        "Image conversion, schema extraction, and vulnerability tools also return "
        "client-side artifacts. Treat local paths as opaque values and execute only "
        "after user intent and required inputs are clear."
    ),
    host="0.0.0.0",
    port=8000,
)

register_all(mcp)


def main():
    logger.info("Starting toku-ai-mcp server using streamable HTTP")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
