import sys
import json
sys.path.insert(0, ".")

from schemas import MasteryState, DomainScore
from agents.syllabus_mapper import run_syllabus_mapper
from agents.question_generator import run_question_generator
from agents.grader import run_grader
from agents.mastery_scorer import run_mastery_scorer
from agents.study_strategy import run_study_strategy


def test_full_session():
    print("=" * 60)
    print("CERTIFICATION PRACTICE MASTERY — PIPELINE TEST")
    print("=" * 60)

    # ── Test 1: Syllabus Mapper ────────────────────────────────
    print("\n[1/6] Testing Syllabus Mapper...")
    syllabus = run_syllabus_mapper("Google Professional Data Engineer")

    assert syllabus.certification.official_name, "FAIL: no cert name"
    assert len(syllabus.domains) >= 3, "FAIL: too few domains"

    total_weight = sum(d.weight_percent for d in syllabus.domains)
    assert total_weight == 100, f"FAIL: weights sum to {total_weight}, not 100"

    print(f"  PASS: {syllabus.certification.official_name}")
    print(f"  PASS: {len(syllabus.domains)} domains, weights sum to {total_weight}")
    for d in syllabus.domains:
        print(f"    - {d.domain_name}: {d.weight_percent}% ({len(d.key_topics)} topics)")

    # ── Test 2: Question Generator (first question) ───────────
    print("\n[2/6] Testing Question Generator (first question)...")
    mastery = MasteryState()
    for d in syllabus.domains:
        mastery.domain_scores[d.domain_name] = DomainScore()

    q1 = run_question_generator(syllabus, mastery, question_number=1)

    assert q1.question_text, "FAIL: no question text"
    assert len(q1.options) == 4, f"FAIL: {len(q1.options)} options instead of 4"
    assert q1.correct_answer in ("A", "B", "C", "D"), f"FAIL: bad correct_answer: {q1.correct_answer}"
    assert q1.domain in [d.domain_name for d in syllabus.domains], f"FAIL: domain '{q1.domain}' not in syllabus"

    print(f"  PASS: generated question in domain '{q1.domain}' ({q1.difficulty})")
    print(f"  PASS: correct answer is {q1.correct_answer}")
    print(f"  Question: {q1.question_text[:100]}...")

    # ── Test 3: Grader (correct answer) ───────────────────────
    print("\n[3/6] Testing Grader (submitting correct answer)...")
    grading_correct = run_grader(q1, q1.correct_answer)

    assert grading_correct.is_correct, "FAIL: correct answer graded as wrong"
    assert grading_correct.error_category is None, "FAIL: error category should be None for correct answer"

    print(f"  PASS: correct answer graded as correct")
    print(f"  Explanation: {grading_correct.explanation[:100]}...")

    # ── Test 4: Grader (wrong answer) ─────────────────────────
    print("\n[4/6] Testing Grader (submitting wrong answer)...")
    wrong_options = [x for x in ("A", "B", "C", "D") if x != q1.correct_answer]
    wrong_answer = wrong_options[0]

    grading_wrong = run_grader(q1, wrong_answer)

    assert not grading_wrong.is_correct, "FAIL: wrong answer graded as correct"
    assert grading_wrong.error_category is not None, "FAIL: no error category for wrong answer"

    print(f"  PASS: wrong answer ({wrong_answer}) graded as incorrect")
    print(f"  PASS: error category = {grading_wrong.error_category}")
    if grading_wrong.concept_gap:
        print(f"  PASS: concept gap = {grading_wrong.concept_gap}")

    # ── Test 5: Mastery Scorer ────────────────────────────────
    print("\n[5/6] Testing Mastery Scorer...")

    # Score the correct answer
    mastery = run_mastery_scorer(mastery, grading_correct, syllabus)
    assert mastery.total_questions == 1, "FAIL: total_questions should be 1"
    assert mastery.total_correct == 1, "FAIL: total_correct should be 1"
    assert mastery.current_streak == 1, "FAIL: streak should be 1"

    # Score the wrong answer
    mastery = run_mastery_scorer(mastery, grading_wrong, syllabus)
    assert mastery.total_questions == 2, "FAIL: total_questions should be 2"
    assert mastery.total_correct == 1, "FAIL: total_correct should still be 1"
    assert mastery.current_streak == 0, "FAIL: streak should reset to 0"
    assert mastery.pass_probability >= 0, "FAIL: pass probability negative"

    print(f"  PASS: 2 questions scored, 1 correct")
    print(f"  PASS: pass probability = {mastery.pass_probability}%")
    print(f"  PASS: weakest domain = {mastery.weakest_domain}")

    # ── Test 6: Study Strategy ────────────────────────────────
    print("\n[6/6] Testing Study Strategy...")

    # Add a few more results so the strategy has something to analyse
    for i in range(3):
        q = run_question_generator(syllabus, mastery, question_number=i + 3)
        g = run_grader(q, q.correct_answer)  # answer all correctly
        mastery = run_mastery_scorer(mastery, g, syllabus)

    strategy = run_study_strategy(mastery, syllabus)

    assert len(strategy) > 100, "FAIL: strategy too short"

    print(f"  PASS: strategy generated ({len(strategy)} chars)")
    print(f"  Preview: {strategy[:200]}...")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ALL 6 TESTS PASSED")
    print(f"Final state: {mastery.total_questions} questions, "
          f"{mastery.total_correct} correct, "
          f"{mastery.pass_probability}% pass probability")
    print("=" * 60)


if __name__ == "__main__":
    test_full_session()