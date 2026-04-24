"""SQLite persistence layer.

Provides storage for sessions, SRS cards, syllabus cache,
and question history. Zero external dependencies — uses stdlib sqlite3.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from config import get_logger

logger = get_logger("Database")

DB_PATH = Path(__file__).parent / "mastery.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin wrapper around SQLite for the certification mastery app."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_tables(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    cert_name    TEXT NOT NULL,
                    syllabus_json TEXT NOT NULL,
                    mastery_json TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS srs_cards (
                    card_id       TEXT PRIMARY KEY,
                    session_id    TEXT NOT NULL,
                    concept       TEXT NOT NULL,
                    domain        TEXT NOT NULL,
                    subtopic      TEXT NOT NULL,
                    ease_factor   REAL NOT NULL DEFAULT 2.5,
                    interval_days INTEGER NOT NULL DEFAULT 1,
                    repetitions   INTEGER NOT NULL DEFAULT 0,
                    next_review   TEXT,
                    last_review   TEXT,
                    quality_history TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS syllabus_cache (
                    cert_key      TEXT PRIMARY KEY,
                    syllabus_json TEXT NOT NULL,
                    cached_at     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS question_history (
                    question_id   TEXT PRIMARY KEY,
                    session_id    TEXT NOT NULL,
                    question_json TEXT NOT NULL,
                    student_answer TEXT,
                    is_correct    INTEGER,
                    grading_json  TEXT,
                    created_at    TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
            """)

    # ── Sessions ──────────────────────────────────────────────

    def create_session(self, cert_name: str, syllabus_json: str, mastery_json: str) -> str:
        """Create a new session and return the session_id."""
        session_id = str(uuid.uuid4())[:8]
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, cert_name, syllabus_json, mastery_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, cert_name, syllabus_json, mastery_json, now, now),
            )
        logger.info(f"Created session {session_id} for '{cert_name}'")
        return session_id

    def save_session(self, session_id: str, mastery_json: str):
        """Update an existing session's mastery state."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET mastery_json = ?, updated_at = ? WHERE session_id = ?",
                (mastery_json, _now_iso(), session_id),
            )

    def load_session(self, session_id: str) -> dict | None:
        """Load a session by ID. Returns dict with all fields or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row:
            return dict(row)
        return None

    def list_sessions(self) -> list[dict]:
        """List all sessions, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT s.session_id, s.cert_name, s.created_at, s.updated_at, "
                "s.mastery_json, "
                "(SELECT COUNT(*) FROM question_history q WHERE q.session_id = s.session_id) as question_count "
                "FROM sessions s ORDER BY s.updated_at DESC"
            ).fetchall()
        results = []
        for row in rows:
            mastery = json.loads(row["mastery_json"])
            results.append({
                "session_id": row["session_id"],
                "cert_name": row["cert_name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "question_count": row["question_count"],
                "pass_probability": mastery.get("pass_probability", 0),
            })
        return results

    def delete_session(self, session_id: str):
        """Delete a session and its related data."""
        with self._connect() as conn:
            conn.execute("DELETE FROM srs_cards WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM question_history WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        logger.info(f"Deleted session {session_id}")

    # ── Syllabus Cache ────────────────────────────────────────

    @staticmethod
    def _normalize_cert_key(cert_name: str) -> str:
        """Normalize a cert name for cache lookups."""
        return cert_name.strip().lower().replace(" ", "_").replace("-", "_")

    def cache_syllabus(self, cert_name: str, syllabus_json: str):
        """Cache a syllabus for a certification name."""
        key = self._normalize_cert_key(cert_name)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO syllabus_cache (cert_key, syllabus_json, cached_at) "
                "VALUES (?, ?, ?)",
                (key, syllabus_json, _now_iso()),
            )
        logger.info(f"Cached syllabus for '{cert_name}' (key: {key})")

    def get_cached_syllabus(self, cert_name: str) -> str | None:
        """Retrieve cached syllabus JSON, or None if not cached."""
        key = self._normalize_cert_key(cert_name)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT syllabus_json FROM syllabus_cache WHERE cert_key = ?", (key,)
            ).fetchone()
        if row:
            logger.info(f"Syllabus cache HIT for '{cert_name}'")
            return row["syllabus_json"]
        logger.info(f"Syllabus cache MISS for '{cert_name}'")
        return None

    # ── SRS Cards ─────────────────────────────────────────────

    def upsert_srs_card(
        self,
        session_id: str,
        card_id: str,
        concept: str,
        domain: str,
        subtopic: str,
        ease_factor: float,
        interval_days: int,
        repetitions: int,
        next_review: str | None,
        last_review: str | None,
        quality_history: list[int],
    ):
        """Create or update an SRS card."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO srs_cards "
                "(card_id, session_id, concept, domain, subtopic, ease_factor, "
                "interval_days, repetitions, next_review, last_review, quality_history) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    card_id, session_id, concept, domain, subtopic,
                    ease_factor, interval_days, repetitions,
                    next_review, last_review, json.dumps(quality_history),
                ),
            )

    def get_due_cards(self, session_id: str) -> list[dict]:
        """Get SRS cards that are due for review (next_review <= now)."""
        now = _now_iso()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM srs_cards WHERE session_id = ? AND next_review <= ? "
                "ORDER BY next_review ASC",
                (session_id, now),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_cards(self, session_id: str) -> list[dict]:
        """Get all SRS cards for a session."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM srs_cards WHERE session_id = ?", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Question History ──────────────────────────────────────

    def save_question(
        self,
        session_id: str,
        question_id: str,
        question_json: str,
        student_answer: str | None = None,
        is_correct: bool | None = None,
        grading_json: str | None = None,
    ):
        """Save a question and its grading result."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO question_history "
                "(question_id, session_id, question_json, student_answer, is_correct, grading_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    question_id, session_id, question_json,
                    student_answer, int(is_correct) if is_correct is not None else None,
                    grading_json, _now_iso(),
                ),
            )

    def get_question_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get question history for a session, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM question_history WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
