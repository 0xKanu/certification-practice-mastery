"""SM-2 Spaced Repetition Algorithm.

Pure implementation of the SuperMemo-2 algorithm for scheduling
concept reviews at optimal intervals. No external dependencies.

Quality scale (mapped from our grading):
  5 = correct, no hesitation
  4 = correct
  3 = correct with difficulty
  2 = incorrect, incomplete knowledge
  1 = incorrect, conceptual misunderstanding
  0 = incorrect, random guess
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from config import get_logger

logger = get_logger("SRS")


def sm2(
    quality: int,
    repetitions: int,
    ease_factor: float,
    interval_days: int,
) -> tuple[int, float, int]:
    """Run one step of the SM-2 algorithm.

    Args:
        quality: Response quality (0-5).
        repetitions: Current number of successful repetitions.
        ease_factor: Current ease factor (>= 1.3).
        interval_days: Current interval in days.

    Returns:
        (new_repetitions, new_ease_factor, new_interval_days)
    """
    if quality < 0 or quality > 5:
        raise ValueError(f"Quality must be 0-5, got {quality}")

    if quality >= 3:
        # Successful recall — increase interval
        new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ef = max(1.3, new_ef)

        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ef)

        return repetitions + 1, new_ef, new_interval
    else:
        # Failed recall — reset
        new_ef = max(1.3, ease_factor - 0.2)
        return 0, new_ef, 1


def grading_to_quality(is_correct: bool, error_category: str | None = None) -> int:
    """Map our grading result to an SM-2 quality score.

    Args:
        is_correct: Whether the answer was correct.
        error_category: Error classification from the grader agent.

    Returns:
        SM-2 quality score (0-5).
    """
    if is_correct:
        return 4  # correct response (we don't track hesitation)

    # Map error categories to quality scores
    category_map = {
        "careless_error": 2,
        "misread_question": 2,
        "incomplete_knowledge": 1,
        "conceptual_misunderstanding": 1,
        "random_guess": 0,
    }
    return category_map.get(error_category, 1)


def make_card_id(session_id: str, concept: str) -> str:
    """Generate a deterministic card ID from session + concept."""
    raw = f"{session_id}:{concept}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def calculate_next_review(interval_days: int) -> str:
    """Calculate the next review datetime as ISO string."""
    return (datetime.now(timezone.utc) + timedelta(days=interval_days)).isoformat()


def update_card_after_review(
    db,
    session_id: str,
    concept: str,
    domain: str,
    subtopic: str,
    is_correct: bool,
    error_category: str | None = None,
):
    """Update (or create) an SRS card after a question is graded.

    This is the main integration point called by the mastery scorer.
    """
    card_id = make_card_id(session_id, concept)
    quality = grading_to_quality(is_correct, error_category)

    # Try to load existing card
    existing_cards = db.get_all_cards(session_id)
    existing = None
    for c in existing_cards:
        if c["card_id"] == card_id:
            existing = c
            break

    if existing:
        reps = existing["repetitions"]
        ef = existing["ease_factor"]
        interval = existing["interval_days"]
        history = json.loads(existing["quality_history"])
    else:
        reps = 0
        ef = 2.5
        interval = 1
        history = []

    # Run SM-2
    new_reps, new_ef, new_interval = sm2(quality, reps, ef, interval)
    history.append(quality)

    next_review = calculate_next_review(new_interval)
    now = datetime.now(timezone.utc).isoformat()

    db.upsert_srs_card(
        session_id=session_id,
        card_id=card_id,
        concept=concept,
        domain=domain,
        subtopic=subtopic,
        ease_factor=new_ef,
        interval_days=new_interval,
        repetitions=new_reps,
        next_review=next_review,
        last_review=now,
        quality_history=history,
    )

    logger.info(
        f"SRS card updated: concept='{concept}', quality={quality}, "
        f"interval={new_interval}d, next_review={next_review[:10]}"
    )
