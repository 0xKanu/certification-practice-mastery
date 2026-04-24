import json
from pathlib import Path
from config import call_llm_json, get_logger
from schemas import GradingOutput, QuestionOutput

logger = get_logger("Agent.Grader")

PROMPT = (Path(__file__).parent.parent / "prompts" / "grader.md").read_text()


def run_grader(
    question: QuestionOutput,
    student_answer: str,
) -> GradingOutput:
    """Agent 3: question + answer → grading + error classification."""
    logger.info(f"Grading answer '{student_answer}' for question '{question.question_id}'...")
    
    context = json.dumps({
        "question": question.model_dump(),
        "student_answer": student_answer.strip().upper(),
    }, indent=2)

    result = call_llm_json(
        system_prompt=PROMPT,
        user_message=context,
        schema=GradingOutput,
        temperature=0,
    )
    
    logger.info(f"Grading complete. Correct: {result.is_correct}")
    return result