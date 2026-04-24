import json
from pathlib import Path
from config import call_llm_json, get_logger
from schemas import GradingOutput, QuestionOutput, ErrorCategory

logger = get_logger("Agent.Grader")

PROMPT = (Path(__file__).parent.parent / "prompts" / "grader.md").read_text()


def grade_deterministic(question: QuestionOutput, student_answer: str) -> GradingOutput:
    """Instant deterministic grading — no LLM call.

    Checks correctness by comparing answers directly.
    Returns a GradingOutput with is_correct set, but no error classification.
    """
    is_correct = student_answer.strip().upper() == question.correct_answer.strip().upper()

    result = GradingOutput(
        question_id=question.question_id,
        domain=question.domain,
        subtopic=question.subtopic,
        is_correct=is_correct,
        student_answer=student_answer.strip().upper(),
        correct_answer=question.correct_answer,
        explanation=question.explanation if is_correct else "",
    )
    logger.info(f"Deterministic grade: {'correct' if is_correct else 'incorrect'}")
    return result


def classify_error(question: QuestionOutput, student_answer: str) -> GradingOutput:
    """LLM-powered error classification — only called for wrong answers.

    Provides error category, reasoning, explanation, and concept gap.
    """
    logger.info(f"Classifying error for question '{question.question_id}'...")

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

    # Ensure correctness is set properly (don't trust the LLM for this)
    result.is_correct = False
    logger.info(f"Error classified: {result.error_category}")
    return result


def run_grader(question: QuestionOutput, student_answer: str) -> GradingOutput:
    """Full grading: deterministic check + LLM error classification if wrong.

    This is the backwards-compatible entry point used by the pipeline test.
    For the orchestrator, use grade_deterministic + classify_error separately.
    """
    grading = grade_deterministic(question, student_answer)

    if not grading.is_correct:
        # Get detailed error classification from LLM
        detailed = classify_error(question, student_answer)
        return detailed

    return grading