import json
from pathlib import Path
from config import call_llm_json
from schemas import QuestionOutput, SyllabusOutput, MasteryState


PROMPT = (Path(__file__).parent.parent / "prompts" / "question_generator.md").read_text()


def run_question_generator(
    syllabus: SyllabusOutput,
    mastery: MasteryState,
    question_number: int,
) -> QuestionOutput:
    """Agent 2: syllabus + mastery state → one practice question."""
    context = json.dumps({
        "syllabus": syllabus.model_dump(),
        "mastery": mastery.model_dump(),
        "question_number": question_number,
    }, indent=2)

    return call_llm_json(
        system_prompt=PROMPT,
        user_message=context,
        schema=QuestionOutput,
        temperature=0.7,
    )