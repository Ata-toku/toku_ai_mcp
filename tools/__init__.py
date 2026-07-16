from tools.image_to_base64 import register as register_standalone_image_to_base64
from tools.base64_to_image import register as register_standalone_base64_to_image
from tools.extract_json_schema import register as register_extract_json_schema
from tools.knowledge_base import register as register_knowledge_base
from tools.run_assessment import register as register_run_assessment
from tools.vulnerability_form import register as register_vulnerability_form


def register_all(mcp):
    """Register every tool on the given FastMCP instance."""
    register_standalone_image_to_base64(mcp)
    register_standalone_base64_to_image(mcp)
    register_extract_json_schema(mcp)
    register_knowledge_base(mcp)
    register_run_assessment(mcp)
    register_vulnerability_form(mcp)
