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


def _calculate_difficulty(pass_probability: int, streak: int) -> str:
    """Calculate difficulty based on pass probability and streak."""
    if pass_probability >= 85 or streak >= 5:
        return "expert"
    elif pass_probability >= 70 or streak >= 3:
        return "hard"
    elif pass_probability >= 40:
        return "medium"
    else:
        return "easy"


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

    # Calculate difficulty based on pass probability
    difficulty = _calculate_difficulty(mastery.pass_probability, mastery.current_streak)

    base_context = {
        "syllabus": syllabus.model_dump(),
        "mastery": mastery.model_dump(),
        "question_number": question_number,
        "difficulty": difficulty,
        "recent_questions": mastery.recent_questions[-10:] if mastery.recent_questions else [],
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
        # Use a weighted domain selection (more weight on weaker domains)
        if mastery.domain_scores:
            # Get weakest domain first
            if mastery.weakest_domain and mastery.weakest_domain in mastery.domain_scores:
                domain = mastery.weakest_domain
            else:
                domain = next(iter(mastery.domain_scores.keys()))
        else:
            domain = "general"
        subtopic = "general"
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
            # Cache the question for future reuse (only non-SRS)
            if db and not srs_review_concept:
                q_domain = question.domain
                q_subtopic = question.subtopic if hasattr(question, 'subtopic') and question.subtopic else "general"
                q_difficulty = question.difficulty
                cache_key = _make_cache_key(q_domain, q_subtopic, q_difficulty, session_id)
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