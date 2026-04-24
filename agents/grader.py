import json
from pathlib import Path
from config import call_llm_json
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

    return call_llm_json(
        system_prompt=PROMPT,
        user_message=context,
        schema=GradingOutput,
        temperature=0,
    )