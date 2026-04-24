"""Unit tests for the agent orchestrator routing decisions."""

import json
import pytest
from unittest.mock import patch, MagicMock
from database import Database
from orchestrator import Orchestrator
from schemas import (
    SyllabusOutput, CertificationMeta, Domain, MasteryState,
    DomainScore, QuestionOutput, Option, GradingOutput,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def orchestrator(db):
    orch = Orchestrator(db)
    yield orch
    orch.shutdown()


@pytest.fixture
def sample_syllabus():
    return SyllabusOutput(
        certification=CertificationMeta(official_name="Test Cert", provider="Test"),
        domains=[
            Domain(domain_name="D1", weight_percent=60, key_topics=["T1"], subtopics=["S1"], confidence="high"),
            Domain(domain_name="D2", weight_percent=40, key_topics=["T2"], subtopics=["S2"], confidence="high"),
        ],
        confidence_overall="high",
    )


@pytest.fixture
def sample_question():
    return QuestionOutput(
        question_id="q1",
        domain="D1",
        subtopic="S1",
        difficulty="medium",
        question_text="What is X?",
        options=[
            Option(label="A", text="Option A"),
            Option(label="B", text="Option B"),
            Option(label="C", text="Option C"),
            Option(label="D", text="Option D"),
        ],
        correct_answer="A",
        explanation="A is correct because...",
        concept_tested="Concept X",
    )


class TestCertSubmission:
    def test_cache_miss_calls_mapper(self, orchestrator, sample_syllabus):
        with patch("orchestrator.run_syllabus_mapper", return_value=sample_syllabus) as mock:
            result = orchestrator.handle_cert_submitted("AWS SAA")
            mock.assert_called_once()
            assert result["cached"] is False
            assert result["syllabus"].certification.official_name == "Test Cert"

    def test_cache_hit_skips_mapper(self, orchestrator, db, sample_syllabus):
        # Pre-cache a syllabus
        db.cache_syllabus("AWS SAA", sample_syllabus.model_dump_json())

        with patch("orchestrator.run_syllabus_mapper") as mock:
            result = orchestrator.handle_cert_submitted("AWS SAA")
            mock.assert_not_called()
            assert result["cached"] is True

    def test_caches_valid_syllabus(self, orchestrator, sample_syllabus):
        with patch("orchestrator.run_syllabus_mapper", return_value=sample_syllabus):
            orchestrator.handle_cert_submitted("AWS SAA")

        # Should be cached now
        cached = orchestrator.db.get_cached_syllabus("AWS SAA")
        assert cached is not None


class TestSessionManagement:
    def test_create_session(self, orchestrator, sample_syllabus):
        result = orchestrator.handle_session_start("AWS SAA", sample_syllabus)
        assert "session_id" in result
        assert result["mastery"].session_id == result["session_id"]
        assert len(result["mastery"].domain_scores) == 2

    def test_resume_session(self, orchestrator, sample_syllabus):
        # Create a session
        start = orchestrator.handle_session_start("AWS SAA", sample_syllabus)
        sid = start["session_id"]

        # Resume it
        result = orchestrator.handle_session_resume(sid)
        assert result is not None
        assert result["cert_name"] == "AWS SAA"
        assert result["mastery"].session_id == sid

    def test_resume_nonexistent_session(self, orchestrator):
        assert orchestrator.handle_session_resume("fake") is None


class TestAnswerSubmission:
    def test_correct_answer_instant_grading(self, orchestrator, sample_syllabus, sample_question):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        mastery = start["mastery"]

        with patch("orchestrator.run_question_generator"):
            result = orchestrator.handle_answer_submitted(
                question=sample_question,
                student_answer="A",
                syllabus=sample_syllabus,
                mastery=mastery,
                question_number=1,
            )

        assert result["grading"].is_correct is True
        assert result["mastery"].total_correct == 1

    def test_wrong_answer_launches_error_classification(self, orchestrator, sample_syllabus, sample_question):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        mastery = start["mastery"]

        with patch("orchestrator.run_question_generator"):
            with patch("orchestrator.classify_error") as mock_classify:
                result = orchestrator.handle_answer_submitted(
                    question=sample_question,
                    student_answer="B",
                    syllabus=sample_syllabus,
                    mastery=mastery,
                    question_number=1,
                )

        assert result["grading"].is_correct is False
        assert orchestrator._error_future is not None

    def test_prefetches_next_question(self, orchestrator, sample_syllabus, sample_question):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        mastery = start["mastery"]

        with patch("orchestrator.run_question_generator") as mock_gen:
            result = orchestrator.handle_answer_submitted(
                question=sample_question,
                student_answer="A",
                syllabus=sample_syllabus,
                mastery=mastery,
                question_number=1,
            )

        # Next question should be pre-generating
        assert orchestrator._prefetched_question is not None

    def test_persists_to_database(self, orchestrator, sample_syllabus, sample_question):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        mastery = start["mastery"]
        sid = start["session_id"]

        with patch("orchestrator.run_question_generator"):
            orchestrator.handle_answer_submitted(
                question=sample_question,
                student_answer="A",
                syllabus=sample_syllabus,
                mastery=mastery,
                question_number=1,
            )

        # Check database
        history = orchestrator.db.get_question_history(sid)
        assert len(history) == 1
        assert history[0]["is_correct"] == 1


class TestSRSIntegration:
    def test_srs_review_flag_checked(self, orchestrator, sample_syllabus, sample_question):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        mastery = start["mastery"]
        mastery.next_is_review = True

        # Add a due SRS card
        orchestrator.db.upsert_srs_card(
            session_id=mastery.session_id,
            card_id="test_card",
            concept="VPC Peering",
            domain="D1",
            subtopic="S1",
            ease_factor=2.5,
            interval_days=1,
            repetitions=0,
            next_review="2020-01-01T00:00:00+00:00",
            last_review=None,
            quality_history=[],
        )

        with patch("orchestrator.run_question_generator", return_value=sample_question) as mock_gen:
            orchestrator.handle_generate_question(sample_syllabus, mastery, 1)
            # Should have been called with SRS review concept
            call_kwargs = mock_gen.call_args
            assert call_kwargs[1].get("srs_review_concept") == "VPC Peering" or \
                   (len(call_kwargs[0]) > 3 and call_kwargs[0][3] == "VPC Peering")

    def test_srs_stats(self, orchestrator, sample_syllabus):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        sid = start["session_id"]

        # No cards yet
        stats = orchestrator.get_srs_stats(sid)
        assert stats["total_cards"] == 0

        # Add some cards
        orchestrator.db.upsert_srs_card(
            session_id=sid, card_id="c1", concept="C1", domain="D1", subtopic="S1",
            ease_factor=2.5, interval_days=1, repetitions=1,
            next_review="2099-01-01T00:00:00+00:00", last_review=None, quality_history=[4],
        )
        orchestrator.db.upsert_srs_card(
            session_id=sid, card_id="c2", concept="C2", domain="D1", subtopic="S1",
            ease_factor=2.5, interval_days=1, repetitions=0,
            next_review="2020-01-01T00:00:00+00:00", last_review=None, quality_history=[],
        )

        stats = orchestrator.get_srs_stats(sid)
        assert stats["total_cards"] == 2
        assert stats["due_cards"] == 1
        assert stats["retention_rate"] == 50


class TestListAndDelete:
    def test_list_sessions(self, orchestrator, sample_syllabus):
        orchestrator.handle_session_start("Cert A", sample_syllabus)
        orchestrator.handle_session_start("Cert B", sample_syllabus)

        sessions = orchestrator.list_sessions()
        assert len(sessions) == 2

    def test_delete_session(self, orchestrator, sample_syllabus):
        start = orchestrator.handle_session_start("Test", sample_syllabus)
        sid = start["session_id"]

        orchestrator.delete_session(sid)
        assert orchestrator.handle_session_resume(sid) is None
