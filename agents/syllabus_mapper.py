import json
from pathlib import Path
from config import call_llm_json
from schemas import SyllabusOutput


PROMPT = (Path(__file__).parent.parent / "prompts" / "syllabus_mapper.md").read_text()


def run_syllabus_mapper(certification_name: str) -> SyllabusOutput:
    """Agent 1: certification name → structured syllabus."""
    return call_llm_json(
        system_prompt=PROMPT,
        user_message=f"Map the syllabus for: {certification_name}",
        schema=SyllabusOutput,
        temperature=0,
    )