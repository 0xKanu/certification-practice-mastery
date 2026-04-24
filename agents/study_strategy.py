import json
from pathlib import Path
from config import call_llm
from schemas import MasteryState, SyllabusOutput


PROMPT = (Path(__file__).parent.parent / "prompts" / "study_strategy.md").read_text()


def run_study_strategy(
    mastery: MasteryState,
    syllabus: SyllabusOutput,
) -> str:
    """Agent 5: mastery state → study recommendations (plain text)."""
    context = json.dumps({
        "mastery": mastery.model_dump(),
        "syllabus": syllabus.model_dump(),
    }, indent=2)

    return call_llm(
        system_prompt=PROMPT,
        user_message=context,
        temperature=0.3,
    )