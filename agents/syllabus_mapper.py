import json
from pathlib import Path
from config import call_llm
from schemas import SyllabusOutput


PROMPT = (Path(__file__).parent.parent / "prompts" / "syllabus_mapper.md").read_text()


def run_syllabus_mapper(certification_name: str) -> SyllabusOutput:
    """Agent 1: certification name → structured syllabus."""
    raw = call_llm(
        system_prompt=PROMPT,
        user_message=f"Map the syllabus for: {certification_name}",
        temperature=0,
    )
    # Strip markdown fences if the LLM wraps in ```json
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    parsed = json.loads(clean)
    return SyllabusOutput(**parsed)