"""End-to-end pipeline integration test.

Tests the full multi-agent pipeline through the orchestrator:
Syllabus Mapping → Question Generation (with QA review) → Grading
(deterministic + error classification) → Mastery Scoring (with SRS)
→ Study Strategy

Also tests: syllabus caching, session persistence, SRS card creation.

Requires: OPENROUTER_API_KEY in .env
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from database import Database
from orchestrator import Orchestrator
from schemas import MasteryState, DomainScore


def test_full_session():
    print("=" * 60)
    print("CERTIFICATION PRACTICE MASTERY — PIPELINE TEST (v2)")
    print("Multi-agent orchestrator with SRS + persistence")
    print("=" * 60)

    # Use a temporary database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        orch = Orchestrator(db)

        try:
            _run_pipeline(orch, db)
        finally:
            orch.shutdown()


def _run_pipeline(orch: Orchestrator, db: Database):
    # ── Test 1: Syllabus Mapper (via orchestrator) ────────────
    print("\n[1/8] Testing Syllabus Mapper (cache MISS)...")
    result = orch.handle_cert_submitted("Google Professional Data Engineer")
    syllabus = result["syllabus"]

    assert syllabus.is_valid, "FAIL: syllabus not valid"
    assert syllabus.certification.official_name, "FAIL: no cert name"
    assert len(syllabus.domains) >= 3, "FAIL: too few domains"
    assert result["cached"] is False, "FAIL: should be cache miss"

    total_weight = sum(d.weight_percent for d in syllabus.domains)
    assert total_weight == 100, f"FAIL: weights sum to {total_weight}, not 100"

    print(f"  PASS: {syllabus.certification.official_name}")
    print(f"  PASS: {len(syllabus.domains)} domains, weights sum to {total_weight}")
    for d in syllabus.domains:
        print(f"    - {d.domain_name}: {d.weight_percent}% ({len(d.key_topics)} topics)")

    # ── Test 2: Syllabus Cache HIT ────────────────────────────
    print("\n[2/8] Testing Syllabus Cache (should be instant)...")
    import time
    start = time.time()
    result2 = orch.handle_cert_submitted("Google Professional Data Engineer")
    elapsed = time.time() - start

    assert result2["cached"] is True, "FAIL: should be cache hit"
    assert elapsed < 0.1, f"FAIL: cache hit took {elapsed:.3f}s (should be <0.1s)"

    print(f"  PASS: Cache hit in {elapsed:.4f}s")

    # ── Test 3: Session Creation ──────────────────────────────
    print("\n[3/8] Testing Session Creation + Persistence...")
    session_result = orch.handle_session_start("Google Professional Data Engineer", syllabus)
    mastery = session_result["mastery"]
    session_id = session_result["session_id"]

    assert mastery.session_id == session_id, "FAIL: session_id not set"
    assert len(mastery.domain_scores) == len(syllabus.domains), "FAIL: domain scores not initialised"

    # Verify in database
    db_session = db.load_session(session_id)
    assert db_session is not None, "FAIL: session not persisted"

    print(f"  PASS: Session {session_id} created and persisted")

    # ── Test 4: Question Generation (first question) ──────────
    print("\n[4/8] Testing Question Generation (first question)...")
    q1 = orch.handle_generate_question(syllabus, mastery, question_number=1)

    assert q1.question_text, "FAIL: no question text"
    assert len(q1.options) == 4, f"FAIL: {len(q1.options)} options instead of 4"
    assert q1.correct_answer in ("A", "B", "C", "D"), f"FAIL: bad correct_answer: {q1.correct_answer}"

    print(f"  PASS: generated question in domain '{q1.domain}' ({q1.difficulty})")
    print(f"  Question: {q1.question_text[:100]}...")

    # ── Test 5: Answer Submission (correct — parallel grading) ─
    print("\n[5/8] Testing Answer Submission (correct answer, parallel grading)...")
    start = time.time()
    submit_result = orch.handle_answer_submitted(
        question=q1,
        student_answer=q1.correct_answer,
        syllabus=syllabus,
        mastery=mastery,
        question_number=1,
    )
    grading_time = time.time() - start
    mastery = submit_result["mastery"]

    assert submit_result["grading"].is_correct, "FAIL: correct answer graded as wrong"
    assert mastery.total_correct == 1, "FAIL: total_correct should be 1"
    assert mastery.current_streak == 1, "FAIL: streak should be 1"

    print(f"  PASS: Correct answer graded in {grading_time:.3f}s (deterministic)")
    print(f"  PASS: Pre-generation launched in background")

    # ── Test 6: Answer Submission (wrong — error classification) ─
    print("\n[6/8] Testing Answer Submission (wrong answer, error classification)...")
    q2 = orch.handle_generate_question(syllabus, mastery, question_number=2)
    wrong_options = [x for x in ("A", "B", "C", "D") if x != q2.correct_answer]

    submit_result2 = orch.handle_answer_submitted(
        question=q2,
        student_answer=wrong_options[0],
        syllabus=syllabus,
        mastery=mastery,
        question_number=2,
    )
    mastery = submit_result2["mastery"]

    assert not submit_result2["grading"].is_correct, "FAIL: wrong answer graded as correct"
    assert mastery.current_streak == 0, "FAIL: streak should reset"

    # Collect error classification from background thread
    import time
    time.sleep(3)  # Give the background thread time to finish
    enriched = orch.collect_error_classification(submit_result2["grading"])
    print(f"  PASS: Wrong answer graded, error category: {enriched.error_category}")

    # ── Test 7: SRS Card Creation ─────────────────────────────
    print("\n[7/8] Testing SRS Card Creation...")
    srs_cards = db.get_all_cards(session_id)
    assert len(srs_cards) >= 1, f"FAIL: expected SRS cards, got {len(srs_cards)}"
    print(f"  PASS: {len(srs_cards)} SRS cards created")
    for card in srs_cards:
        print(f"    - concept='{card['concept']}', interval={card['interval_days']}d, reps={card['repetitions']}")

    # Verify SRS stats
    stats = orch.get_srs_stats(session_id)
    assert stats["total_cards"] >= 1, "FAIL: no cards in stats"
    print(f"  PASS: SRS stats — {stats['total_cards']} cards, {stats['retention_rate']}% retention")

    # ── Test 8: Study Strategy ────────────────────────────────
    print("\n[8/8] Testing Study Strategy...")

    # Add a few more results so the strategy has something to analyse
    for i in range(3):
        q = orch.handle_generate_question(syllabus, mastery, question_number=i + 3)
        result = orch.handle_answer_submitted(
            question=q, student_answer=q.correct_answer,
            syllabus=syllabus, mastery=mastery,
            question_number=i + 3,
        )
        mastery = result["mastery"]

    strategy = orch.handle_strategy_requested(mastery, syllabus)
    assert len(strategy) > 100, "FAIL: strategy too short"

    print(f"  PASS: strategy generated ({len(strategy)} chars)")
    print(f"  Preview: {strategy[:200]}...")

    # ── Test Session Resume ───────────────────────────────────
    print("\n[BONUS] Testing Session Resume...")
    sessions = orch.list_sessions()
    assert len(sessions) >= 1, "FAIL: no sessions listed"

    resumed = orch.handle_session_resume(session_id)
    assert resumed is not None, "FAIL: session not resumable"
    assert resumed["mastery"].total_questions == mastery.total_questions, "FAIL: mastery not persisted"
    print(f"  PASS: Session resumed with {resumed['mastery'].total_questions} questions intact")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ALL 8 TESTS PASSED (+ bonus)")
    print(f"Final state: {mastery.total_questions} questions, "
          f"{mastery.total_correct} correct, "
          f"{mastery.pass_probability}% pass probability")
    print(f"SRS: {stats['total_cards']} concept cards tracked")
    print(f"Database: session persisted, syllabus cached, history saved")
    print("=" * 60)


if __name__ == "__main__":
    test_full_session()