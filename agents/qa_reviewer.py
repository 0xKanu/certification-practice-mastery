import json
from pathlib import Path
from config import call_llm_json, get_logger
from schemas import QAReviewOutput, QuestionOutput

logger = get_logger("Agent.QAReviewer")

PROMPT = (Path(__file__).parent.parent / "prompts" / "qa_reviewer.md").read_text()


def run_qa_reviewer(question: QuestionOutput) -> QAReviewOutput:
    """Agent: Evaluates a generated question and approves or critiques it."""
    logger.info("Reviewing generated question for quality...")
    
    context = json.dumps({
        "question": question.model_dump()
    }, indent=2)

    result = call_llm_json(
        system_prompt=PROMPT,
        user_message=context,
        schema=QAReviewOutput,
        temperature=0,
    )
    
    logger.info(f"QA Review complete. Approved: {result.approved}")
    return result
