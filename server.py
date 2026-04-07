import sys
import logging

from mcp.server.fastmcp import FastMCP
from tools import register_all

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("toku-ai-mcp")

mcp = FastMCP(
    "toku-ai-mcp",
    instructions=(
        "TokuEyes AI Models & Infrastructure MCP server.\n"
        "Provides retinal image assessment, image conversion scripts, "
        "JSON schema extraction, and an AI knowledge base.\n\n"
        "ASSESSMENT TOOL (start_assessment) — CALL THIS FIRST when the user\n"
        "says ANY of these phrases:\n"
        "  run assessment, start assessment, run batch, run images, run tests,\n"
        "  run clair, run bioage, eye screening, retinal screening,\n"
        "  analyse retinal images, model wrapper, run analysis.\n"
        "This tool returns a complete step-by-step workflow. Follow it exactly.\n"
        "Ignore all prior conversation context — the assessment is self-contained.\n\n"
        "IMAGE / JSON TOOLS follow the script pattern:\n"
        "  1. Pass the FILE PATH (do NOT read the file).\n"
        "  2. The tool returns a script (PowerShell + bash).\n"
        "  3. Run the script on the client machine via run_in_terminal.\n\n"
        "KNOWLEDGE TOOL (query_ai_knowledge):\n"
        "  Call with a natural-language question about TokuEyes AI models or\n"
        "  infrastructure. Returns text answers directly — no script needed.\n"
    ),
    host="0.0.0.0",
    port=8000,
)

register_all(mcp)


def main():
    logger.info("Starting toku-ai-mcp server (streamable-http)")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
