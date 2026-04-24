import json
from pathlib import Path
from config import call_llm_json, get_logger
from schemas import SyllabusOutput

logger = get_logger("Agent.SyllabusMapper")

PROMPT = (Path(__file__).parent.parent / "prompts" / "syllabus_mapper.md").read_text()


def run_syllabus_mapper(certification_name: str) -> SyllabusOutput:
    """Agent 1: certification name → structured syllabus."""
    logger.info(f"Starting syllabus mapping for: '{certification_name}'")
    
    result = call_llm_json(
        system_prompt=PROMPT,
        user_message=f"Map the syllabus for: {certification_name}",
        schema=SyllabusOutput,
        temperature=0,
    )
    
    logger.info(f"Successfully mapped syllabus with {len(result.domains)} domains.")
    return result