import json
from pathlib import Path
from config import call_llm
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

    raw = call_llm(
        system_prompt=PROMPT,
        user_message=context,
        temperature=0.7,
    )

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    parsed = json.loads(clean)
    return QuestionOutput(**parsed)