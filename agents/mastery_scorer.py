from schemas import MasteryState, DomainScore, SyllabusOutput, GradingOutput
from config import get_logger

logger = get_logger("Agent.MasteryScorer")

def run_mastery_scorer(
    current_state: MasteryState,
    grading: GradingOutput,
    syllabus: SyllabusOutput,
    db=None,
) -> MasteryState:
    """Agent 4: update mastery state with new grading result.

    This is pure arithmetic. No LLM call. Deterministic, fast, free.
    Optionally updates SRS cards if a database is provided.
    """
    logger.info(f"Updating mastery state for domain '{grading.domain}'...")
    domain = grading.domain

    # Get or create domain score
    if domain not in current_state.domain_scores:
        current_state.domain_scores[domain] = DomainScore()

    ds = current_state.domain_scores[domain]

    # Update counts
    ds.attempted += 1
    if grading.is_correct:
        ds.correct += 1

    # Update recent results (keep last 5)
    ds.recent.append(grading.is_correct)
    if len(ds.recent) > 5:
        ds.recent = ds.recent[-5:]

    # Update difficulty trend
    if len(ds.recent) >= 3 and all(ds.recent[-3:]):
        ds.difficulty_trend = "increasing"
    elif len(ds.recent) >= 2 and not any(ds.recent[-2:]):
        ds.difficulty_trend = "decreasing"
    else:
        ds.difficulty_trend = "stable"

    # Update mastery percent
    if ds.attempted >= 3:
        ds.mastery_percent = round(ds.correct / ds.attempted * 100)
    else:
        ds.mastery_percent = 50  # not enough data

    # Update session totals
    current_state.total_questions += 1
    if grading.is_correct:
        current_state.total_correct += 1
        current_state.current_streak += 1
    else:
        current_state.current_streak = 0

    # Ensure all syllabus domains exist in scores (even if not yet tested)
    for d in syllabus.domains:
        if d.domain_name not in current_state.domain_scores:
            current_state.domain_scores[d.domain_name] = DomainScore()

    # Calculate pass probability (weighted average)
    weight_map = {d.domain_name: d.weight_percent for d in syllabus.domains}
    total_weighted = 0.0
    for name, score in current_state.domain_scores.items():
        weight = weight_map.get(name, 0)
        total_weighted += weight * (score.mastery_percent / 100)

    current_state.pass_probability = round(total_weighted)

    # Find weakest domain (only among tested domains)
    tested = {
        k: v for k, v in current_state.domain_scores.items() if v.attempted > 0
    }
    if tested:
        weakest = min(tested.items(), key=lambda x: x[1].mastery_percent)
        current_state.weakest_domain = weakest[0]

    # ── SRS Card Update ───────────────────────────────────────
    if db and current_state.session_id:
        try:
            from srs import update_card_after_review
            concept = grading.concept_gap or grading.subtopic
            error_cat = grading.error_category.value if grading.error_category else None
            update_card_after_review(
                db=db,
                session_id=current_state.session_id,
                concept=concept,
                domain=grading.domain,
                subtopic=grading.subtopic,
                is_correct=grading.is_correct,
                error_category=error_cat,
            )
        except Exception as e:
            logger.warning(f"Failed to update SRS card: {e}")

    # ── SRS Review Scheduling ─────────────────────────────────
    # Every 5th question, check if there are due SRS cards
    if db and current_state.session_id and current_state.total_questions % 5 == 0:
        try:
            due_cards = db.get_due_cards(current_state.session_id)
            if due_cards:
                current_state.next_is_review = True
                logger.info(f"SRS: {len(due_cards)} cards due for review, next question will be a review.")
        except Exception as e:
            logger.warning(f"Failed to check SRS due cards: {e}")

    return current_state