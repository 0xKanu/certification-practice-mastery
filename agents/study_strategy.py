import json
from pathlib import Path
from config import call_llm, get_logger
from schemas import MasteryState, SyllabusOutput

logger = get_logger("Agent.StudyStrategy")

PROMPT = (Path(__file__).parent.parent / "prompts" / "study_strategy.md").read_text()


def run_study_strategy(
    mastery: MasteryState,
    syllabus: SyllabusOutput,
) -> str:
    """Agent 5: mastery state → study recommendations (plain text)."""
    logger.info("Generating personalized study strategy...")
    
    context = json.dumps({
        "mastery": mastery.model_dump(),
        "syllabus": syllabus.model_dump(),
    }, indent=2)

    result = call_llm(
        system_prompt=PROMPT,
        user_message=context,
        temperature=0.3,
    )
    
    logger.info("Study strategy successfully generated.")
    return result