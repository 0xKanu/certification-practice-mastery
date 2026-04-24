import json
from pathlib import Path
from config import call_llm
from schemas import GradingOutput, QuestionOutput


PROMPT = (Path(__file__).parent.parent / "prompts" / "grader.md").read_text()


def run_grader(
    question: QuestionOutput,
    student_answer: str,
) -> GradingOutput:
    """Agent 3: question + answer → grading + error classification."""
    context = json.dumps({
        "question": question.model_dump(),
        "student_answer": student_answer.strip().upper(),
    }, indent=2)

    raw = call_llm(
        system_prompt=PROMPT,
        user_message=context,
        temperature=0,
    )

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    parsed = json.loads(clean)
    return GradingOutput(**parsed)