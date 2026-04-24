"""Unit tests for the SM-2 spaced repetition algorithm."""

import pytest
from srs import sm2, grading_to_quality, make_card_id


class TestSM2Algorithm:
    def test_first_correct_review_interval_1(self):
        reps, ef, interval = sm2(quality=4, repetitions=0, ease_factor=2.5, interval_days=1)
        assert reps == 1
        assert interval == 1

    def test_second_correct_review_interval_6(self):
        reps, ef, interval = sm2(quality=4, repetitions=1, ease_factor=2.5, interval_days=1)
        assert reps == 2
        assert interval == 6

    def test_third_correct_review_uses_ef_multiplier(self):
        reps, ef, interval = sm2(quality=4, repetitions=2, ease_factor=2.5, interval_days=6)
        assert reps == 3
        assert interval == round(6 * ef)

    def test_perfect_quality_increases_ease(self):
        _, ef, _ = sm2(quality=5, repetitions=2, ease_factor=2.5, interval_days=6)
        assert ef > 2.5

    def test_low_quality_correct_decreases_ease(self):
        _, ef, _ = sm2(quality=3, repetitions=2, ease_factor=2.5, interval_days=6)
        assert ef < 2.5

    def test_incorrect_resets_repetitions(self):
        reps, ef, interval = sm2(quality=2, repetitions=5, ease_factor=2.5, interval_days=30)
        assert reps == 0
        assert interval == 1

    def test_incorrect_decreases_ease(self):
        _, ef, _ = sm2(quality=1, repetitions=3, ease_factor=2.5, interval_days=10)
        assert ef == 2.3

    def test_ease_factor_never_below_1_3(self):
        _, ef, _ = sm2(quality=0, repetitions=0, ease_factor=1.3, interval_days=1)
        assert ef >= 1.3

        _, ef2, _ = sm2(quality=0, repetitions=0, ease_factor=1.4, interval_days=1)
        assert ef2 >= 1.3

    def test_invalid_quality_raises(self):
        with pytest.raises(ValueError):
            sm2(quality=6, repetitions=0, ease_factor=2.5, interval_days=1)
        with pytest.raises(ValueError):
            sm2(quality=-1, repetitions=0, ease_factor=2.5, interval_days=1)

    def test_interval_progression(self):
        """Simulate a learner getting everything right with quality 4."""
        reps, ef, interval = 0, 2.5, 1
        expected_intervals = [1, 6]  # first two are fixed

        for i in range(5):
            reps, ef, interval = sm2(4, reps, ef, interval)
            if i < 2:
                assert interval == expected_intervals[i]
            else:
                # After rep 2, intervals should keep growing
                assert interval > 6

    def test_quality_boundary_3_is_pass(self):
        """Quality 3 should count as a pass (reps increment)."""
        reps, _, _ = sm2(quality=3, repetitions=0, ease_factor=2.5, interval_days=1)
        assert reps == 1

    def test_quality_boundary_2_is_fail(self):
        """Quality 2 should count as a fail (reps reset)."""
        reps, _, interval = sm2(quality=2, repetitions=3, ease_factor=2.5, interval_days=10)
        assert reps == 0
        assert interval == 1


class TestGradingToQuality:
    def test_correct_answer(self):
        assert grading_to_quality(True) == 4

    def test_wrong_careless(self):
        assert grading_to_quality(False, "careless_error") == 2

    def test_wrong_misread(self):
        assert grading_to_quality(False, "misread_question") == 2

    def test_wrong_incomplete(self):
        assert grading_to_quality(False, "incomplete_knowledge") == 1

    def test_wrong_conceptual(self):
        assert grading_to_quality(False, "conceptual_misunderstanding") == 1

    def test_wrong_random(self):
        assert grading_to_quality(False, "random_guess") == 0

    def test_wrong_unknown_category(self):
        assert grading_to_quality(False, "some_unknown") == 1


class TestCardId:
    def test_deterministic(self):
        id1 = make_card_id("session1", "VPC Peering")
        id2 = make_card_id("session1", "VPC Peering")
        assert id1 == id2

    def test_different_for_different_concepts(self):
        id1 = make_card_id("session1", "VPC Peering")
        id2 = make_card_id("session1", "S3 Lifecycle")
        assert id1 != id2

    def test_different_for_different_sessions(self):
        id1 = make_card_id("session1", "VPC Peering")
        id2 = make_card_id("session2", "VPC Peering")
        assert id1 != id2
