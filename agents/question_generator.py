import json
import logging
from pathlib import Path
from config import call_llm_json, get_logger
from schemas import QuestionOutput, SyllabusOutput, MasteryState
from database import Database
from agents.qa_reviewer import run_qa_reviewer

logger = get_logger("Agent.QuestionGenerator")

PROMPT = (Path(__file__).parent.parent / "prompts" / "question_generator.md").read_text()

QUESTION_CACHE_TTL_DAYS = 7


def _make_cache_key(domain: str, subtopic: str, difficulty: str, session_id: str | None) -> str:
    """Create a cache key from domain, subtopic, difficulty, and session prefix."""
    session_prefix = session_id[:8] if session_id else "new"
    return f"{domain}_{subtopic}_{difficulty}_{session_prefix}"


def run_question_generator(
    syllabus: SyllabusOutput,
    mastery: MasteryState,
    question_number: int,
    srs_review_concept: str | None = None,
    srs_review_domain: str | None = None,
    db: Database | None = None,
) -> QuestionOutput:
    """Agent 2: syllabus + mastery state → one practice question (with QA loop).

    If srs_review_concept is provided, generates a question specifically
    targeting that concept for spaced repetition review.

    Uses question caching when db is provided to cache/reuse questions by
    (domain, subtopic, difficulty, session_id).
    """
    mode = "SRS REVIEW" if srs_review_concept else "NEW"
    logger.info(f"Generating question #{question_number} (mode: {mode})...")

    session_id = mastery.session_id if mastery else None

    base_context = {
        "syllabus": syllabus.model_dump(),
        "mastery": mastery.model_dump(),
        "question_number": question_number,
    }

    # Add SRS review context if this is a review question
    if srs_review_concept:
        base_context["srs_review"] = {
            "concept": srs_review_concept,
            "domain": srs_review_domain,
            "instruction": (
                f"This is a SPACED REPETITION REVIEW. You MUST generate a question "
                f"that specifically tests the concept: '{srs_review_concept}' "
                f"in domain '{srs_review_domain}'. The student has seen this concept "
                f"before and needs to be re-tested for long-term retention."
            ),
        }

    current_context = json.dumps(base_context, indent=2)
    max_retries = 3

    # Try cache first (only for non-SRS review questions)
    if db and not srs_review_concept:
        # Use the first domain from mastery as the focus domain
        domain = next(iter(mastery.domain_scores.keys()), "general") if mastery.domain_scores else "general"
        subtopic = "general"
        difficulty = "medium"
        cache_key = _make_cache_key(domain, subtopic, difficulty, session_id)
        cached = db.get_cached_question(cache_key)
        if cached:
            logger.info(f"Cache HIT, returning cached question")
            return QuestionOutput.model_validate_json(cached)

    for attempt in range(max_retries):
        # 1. Generate the question
        question = call_llm_json(
            system_prompt=PROMPT,
            user_message=current_context,
            schema=QuestionOutput,
            temperature=0.7,
        )

        # 2. QA Review
        review = run_qa_reviewer(question)

        if review.approved:
            logger.info(f"Question #{question_number} generated and QA approved.")
            # Cache the question for future reuse
            if db and not srs_review_concept:
                domain = question.domain
                subtopic = question.subtopic if hasattr(question, 'subtopic') and question.subtopic else "general"
                difficulty = question.difficulty
                cache_key = _make_cache_key(domain, subtopic, difficulty, session_id)
                db.cache_question(cache_key, question.model_dump_json())
                logger.info(f"Cached question with key: '{cache_key}'")
            return question

        # 3. If rejected, append critique to the prompt context for the next iteration
        logger.warning(f"QA Review failed (Attempt {attempt + 1}/{max_retries}): {review.critique}")

        retry_message = (
            "The previous question you generated was REJECTED by the QA Reviewer.\n"
            f"Critique: {review.critique}\n\n"
            "Please generate a NEW question addressing this critique, ensuring absolute correctness and clarity."
        )

        # Update context to include the critique
        updated_context = dict(base_context)
        updated_context["qa_reviewer_feedback"] = retry_message
        current_context = json.dumps(updated_context, indent=2)

    # If we exhaust retries, return the last generated question anyway as a fallback
    logger.warning("Max QA retries exhausted. Returning last generated question.")
    return question