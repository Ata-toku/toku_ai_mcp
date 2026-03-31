from tools.image_to_base64 import register as register_image_to_base64
from tools.base64_to_image import register as register_base64_to_image
from tools.extract_json_schema import register as register_extract_json_schema
from tools.ai_knowledge import register as register_ai_knowledge


def register_all(mcp):
    """Register every tool on the given FastMCP instance."""
    register_image_to_base64(mcp)
    register_base64_to_image(mcp)
    register_extract_json_schema(mcp)
    register_ai_knowledge(mcp)
