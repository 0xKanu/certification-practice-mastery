"""Unit tests for the SQLite persistence layer."""

import json
import os
import tempfile
import pytest
from database import Database


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_mastery.db"
    return Database(db_path)


class TestSessions:
    def test_create_and_load_session(self, db):
        sid = db.create_session("AWS SAA", '{"domains": []}', '{"pass_probability": 0}')
        assert len(sid) == 8

        session = db.load_session(sid)
        assert session is not None
        assert session["cert_name"] == "AWS SAA"
        assert json.loads(session["syllabus_json"]) == {"domains": []}
        assert json.loads(session["mastery_json"]) == {"pass_probability": 0}

    def test_load_nonexistent_session(self, db):
        assert db.load_session("nonexistent") is None

    def test_save_session_updates_mastery(self, db):
        sid = db.create_session("AWS SAA", '{}', '{"pass_probability": 0}')
        db.save_session(sid, '{"pass_probability": 75}')

        session = db.load_session(sid)
        assert json.loads(session["mastery_json"])["pass_probability"] == 75

    def test_list_sessions_ordered_by_recent(self, db):
        sid1 = db.create_session("Cert A", '{}', '{"pass_probability": 10}')
        sid2 = db.create_session("Cert B", '{}', '{"pass_probability": 80}')

        # Update sid1 to make it most recent
        db.save_session(sid1, '{"pass_probability": 50}')

        sessions = db.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == sid1  # most recently updated
        assert sessions[0]["pass_probability"] == 50

    def test_delete_session(self, db):
        sid = db.create_session("AWS SAA", '{}', '{}')
        db.delete_session(sid)
        assert db.load_session(sid) is None


class TestSyllabusCache:
    def test_cache_and_retrieve(self, db):
        syllabus = '{"certification": {"name": "AWS SAA"}}'
        db.cache_syllabus("AWS Solutions Architect Associate", syllabus)

        result = db.get_cached_syllabus("AWS Solutions Architect Associate")
        assert result == syllabus

    def test_cache_miss(self, db):
        assert db.get_cached_syllabus("nonexistent cert") is None

    def test_normalization(self, db):
        db.cache_syllabus("AWS SAA", '{"data": 1}')

        # Different casing/spacing should still hit cache
        assert db.get_cached_syllabus("  AWS SAA  ") is not None
        assert db.get_cached_syllabus("aws saa") is not None
        assert db.get_cached_syllabus("AWS-SAA") is not None

    def test_cache_overwrite(self, db):
        db.cache_syllabus("AWS SAA", '{"version": 1}')
        db.cache_syllabus("AWS SAA", '{"version": 2}')

        result = db.get_cached_syllabus("AWS SAA")
        assert json.loads(result)["version"] == 2


class TestSRSCards:
    def test_upsert_and_retrieve(self, db):
        sid = db.create_session("Test", '{}', '{}')
        db.upsert_srs_card(
            session_id=sid,
            card_id="card1",
            concept="VPC Peering",
            domain="Networking",
            subtopic="VPC",
            ease_factor=2.5,
            interval_days=1,
            repetitions=0,
            next_review="2025-01-01T00:00:00+00:00",
            last_review=None,
            quality_history=[4],
        )

        cards = db.get_all_cards(sid)
        assert len(cards) == 1
        assert cards[0]["concept"] == "VPC Peering"
        assert cards[0]["ease_factor"] == 2.5

    def test_get_due_cards(self, db):
        sid = db.create_session("Test", '{}', '{}')

        # Card due in the past
        db.upsert_srs_card(
            session_id=sid, card_id="past", concept="Past Concept",
            domain="D1", subtopic="S1", ease_factor=2.5, interval_days=1,
            repetitions=1, next_review="2020-01-01T00:00:00+00:00",
            last_review=None, quality_history=[],
        )

        # Card due in the future
        db.upsert_srs_card(
            session_id=sid, card_id="future", concept="Future Concept",
            domain="D1", subtopic="S1", ease_factor=2.5, interval_days=1,
            repetitions=1, next_review="2099-01-01T00:00:00+00:00",
            last_review=None, quality_history=[],
        )

        due = db.get_due_cards(sid)
        assert len(due) == 1
        assert due[0]["card_id"] == "past"

    def test_upsert_overwrites(self, db):
        sid = db.create_session("Test", '{}', '{}')
        db.upsert_srs_card(
            session_id=sid, card_id="c1", concept="Concept",
            domain="D1", subtopic="S1", ease_factor=2.5, interval_days=1,
            repetitions=0, next_review=None, last_review=None, quality_history=[],
        )
        db.upsert_srs_card(
            session_id=sid, card_id="c1", concept="Concept",
            domain="D1", subtopic="S1", ease_factor=2.8, interval_days=6,
            repetitions=1, next_review=None, last_review=None, quality_history=[4],
        )

        cards = db.get_all_cards(sid)
        assert len(cards) == 1
        assert cards[0]["ease_factor"] == 2.8
        assert cards[0]["interval_days"] == 6


class TestQuestionHistory:
    def test_save_and_retrieve(self, db):
        sid = db.create_session("Test", '{}', '{}')
        db.save_question(
            session_id=sid,
            question_id="q1",
            question_json='{"text": "What is EC2?"}',
            student_answer="A",
            is_correct=True,
            grading_json='{"is_correct": true}',
        )

        history = db.get_question_history(sid)
        assert len(history) == 1
        assert history[0]["question_id"] == "q1"
        assert history[0]["is_correct"] == 1

    def test_history_ordered_recent_first(self, db):
        sid = db.create_session("Test", '{}', '{}')
        db.save_question(sid, "q1", '{}', "A", True, '{}')
        db.save_question(sid, "q2", '{}', "B", False, '{}')

        history = db.get_question_history(sid)
        assert history[0]["question_id"] == "q2"  # most recent first

    def test_history_respects_limit(self, db):
        sid = db.create_session("Test", '{}', '{}')
        for i in range(10):
            db.save_question(sid, f"q{i}", '{}', "A", True, '{}')

        history = db.get_question_history(sid, limit=3)
        assert len(history) == 3
