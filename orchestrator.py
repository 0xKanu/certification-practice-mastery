"""Event-driven agent orchestrator.

Routes events to agents, manages parallel execution, and makes
autonomous routing decisions based on state. This is the core
architectural piece that makes the system genuinely multi-agent.

Key capabilities:
- Conditional routing (cache hits, SRS scheduling, QA retry budget)
- Parallel execution (grade + generate next question simultaneously)
- Autonomous SRS review weaving (every 5th question)
- Pre-generation pipeline (next question cooks while user reads feedback)
"""

import json
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
from config import get_logger
from database import Database
from schemas import (
    MasteryState, SyllabusOutput, QuestionOutput, GradingOutput,
    DomainScore, AppStage,
)
from agents.syllabus_mapper import run_syllabus_mapper
from agents.question_generator import run_question_generator
from agents.grader import grade_deterministic, classify_error
from agents.mastery_scorer import run_mastery_scorer
from agents.study_strategy import run_study_strategy

logger = get_logger("Orchestrator")


class Event(str, Enum):
    """Events that drive orchestrator routing decisions."""
    CERT_SUBMITTED = "cert_submitted"
    SESSION_RESUMED = "session_resumed"
    SYLLABUS_ACCEPTED = "syllabus_accepted"
    SYLLABUS_REJECTED = "syllabus_rejected"
    QUESTION_NEEDED = "question_needed"
    ANSWER_SUBMITTED = "answer_submitted"
    STRATEGY_REQUESTED = "strategy_requested"


class Orchestrator:
    """Event-driven agent orchestrator with parallel execution.

    Routes events to the appropriate agents, manages state transitions,
    and makes autonomous routing decisions (cache hits, SRS scheduling,
    parallel grading + generation).
    """

    def __init__(self, db: Database):
        self.db = db
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._prefetched_question: Future | None = None
        self._error_future: Future | None = None

    def shutdown(self):
        """Cleanup the thread pool."""
        self._executor.shutdown(wait=False)

    # ── Main Router ───────────────────────────────────────────

    def handle_cert_submitted(self, cert_name: str) -> dict:
        """Handle a certification name submission.

        Routing decision: check syllabus cache before calling LLM.
        """
        logger.info(f"Event: CERT_SUBMITTED — '{cert_name}'")

        # Decision: is this cert cached?
        cached = self.db.get_cached_syllabus(cert_name)
        if cached:
            logger.info("Route: CACHE HIT — skipping syllabus mapper LLM call")
            syllabus = SyllabusOutput(**json.loads(cached))
            return {"syllabus": syllabus, "cached": True}

        # Route to syllabus mapper agent
        logger.info("Route: CACHE MISS — calling syllabus mapper agent")
        syllabus = run_syllabus_mapper(cert_name)

        if syllabus.is_valid:
            # Cache for future use
            self.db.cache_syllabus(cert_name, syllabus.model_dump_json())
            logger.info("Syllabus cached for future sessions")

        return {"syllabus": syllabus, "cached": False}

    def handle_session_start(
        self, cert_name: str, syllabus: SyllabusOutput
    ) -> dict:
        """Create a new session and initialise mastery state."""
        mastery = MasteryState()
        for d in syllabus.domains:
            mastery.domain_scores[d.domain_name] = DomainScore()

        session_id = self.db.create_session(
            cert_name=cert_name,
            syllabus_json=syllabus.model_dump_json(),
            mastery_json=mastery.model_dump_json(),
        )
        mastery.session_id = session_id
        logger.info(f"Session created: {session_id}")

        return {"session_id": session_id, "mastery": mastery}

    def handle_session_resume(self, session_id: str) -> dict | None:
        """Resume an existing session from the database."""
        logger.info(f"Event: SESSION_RESUMED — {session_id}")

        session = self.db.load_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            return None

        syllabus = SyllabusOutput(**json.loads(session["syllabus_json"]))
        mastery = MasteryState(**json.loads(session["mastery_json"]))
        mastery.session_id = session_id

        return {
            "syllabus": syllabus,
            "mastery": mastery,
            "cert_name": session["cert_name"],
        }

    def handle_generate_question(
        self,
        syllabus: SyllabusOutput,
        mastery: MasteryState,
        question_number: int,
    ) -> QuestionOutput:
        """Generate a question, checking for pre-fetched or SRS review.

        Routing decisions:
        1. If a pre-fetched question is ready, serve it instantly
        2. If SRS cards are due, generate a review question
        3. Otherwise, generate a new adaptive question
        """
        logger.info(f"Event: QUESTION_NEEDED — #{question_number}")

        # Decision 1: is a pre-fetched question ready?
        if self._prefetched_question is not None:
            try:
                if self._prefetched_question.done():
                    question = self._prefetched_question.result()
                    self._prefetched_question = None
                    logger.info("Route: PRE-FETCHED question served (instant)")
                    return question
            except Exception as e:
                logger.warning(f"Pre-fetched question failed: {e}")
                self._prefetched_question = None

        # Decision 2: is this an SRS review question?
        srs_concept = None
        srs_domain = None
        if mastery.next_is_review and mastery.session_id:
            due_cards = self.db.get_due_cards(mastery.session_id)
            if due_cards:
                card = due_cards[0]
                srs_concept = card["concept"]
                srs_domain = card["domain"]
                mastery.srs_review_count += 1
                logger.info(f"Route: SRS REVIEW — concept='{srs_concept}'")
            mastery.next_is_review = False

        # Generate question (new or SRS review)
        question = run_question_generator(
            syllabus=syllabus,
            mastery=mastery,
            question_number=question_number,
            srs_review_concept=srs_concept,
            srs_review_domain=srs_domain,
        )
        return question

    def handle_answer_submitted(
        self,
        question: QuestionOutput,
        student_answer: str,
        syllabus: SyllabusOutput,
        mastery: MasteryState,
        question_number: int,
    ) -> dict:
        """Handle answer submission with parallel execution.

        This is the key latency optimisation:
        1. Deterministic correctness check (INSTANT)
        2. Update mastery scorer (INSTANT, deterministic)
        3. Launch LLM error classification in background (if wrong)
        4. Launch next question generation in background (PARALLEL)
        5. Return grading immediately — next question is cooking

        The user sees grading feedback while the next question generates.
        """
        logger.info(f"Event: ANSWER_SUBMITTED — '{student_answer}'")

        # Step 1: INSTANT deterministic grading
        grading = grade_deterministic(question, student_answer)
        logger.info(f"Step 1 (instant): correct={grading.is_correct}")

        # Step 2: Launch error classification in background (if wrong)
        if not grading.is_correct:
            self._error_future = self._executor.submit(
                classify_error, question, student_answer
            )
            logger.info("Step 2: Error classification launched in background")

        # Step 3: Update mastery scorer (instant, deterministic)
        mastery = run_mastery_scorer(mastery, grading, syllabus, db=self.db)
        logger.info(f"Step 3 (instant): mastery updated, pass_prob={mastery.pass_probability}%")

        # Step 4: Save to database
        if mastery.session_id:
            self.db.save_session(mastery.session_id, mastery.model_dump_json())
            self.db.save_question(
                session_id=mastery.session_id,
                question_id=question.question_id,
                question_json=question.model_dump_json(),
                student_answer=student_answer,
                is_correct=grading.is_correct,
                grading_json=grading.model_dump_json(),
            )

        # Step 5: Pre-generate next question in background (PARALLEL)
        next_q_number = question_number + 1

        # Determine if next should be SRS review
        srs_concept = None
        srs_domain = None
        if mastery.next_is_review and mastery.session_id:
            due_cards = self.db.get_due_cards(mastery.session_id)
            if due_cards:
                card = due_cards[0]
                srs_concept = card["concept"]
                srs_domain = card["domain"]
                mastery.srs_review_count += 1
                logger.info(f"Pre-gen: will be SRS review for '{srs_concept}'")
            mastery.next_is_review = False

        self._prefetched_question = self._executor.submit(
            run_question_generator,
            syllabus, mastery, next_q_number,
            srs_concept, srs_domain,
        )
        logger.info("Step 5: Next question pre-generation launched in background")

        # Track recent questions
        mastery.recent_questions.append(question.question_text)
        if len(mastery.recent_questions) > 15:
            mastery.recent_questions.pop(0)

        return {
            "grading": grading,
            "mastery": mastery,
        }

    def collect_error_classification(self, base_grading: GradingOutput) -> GradingOutput:
        """Collect error classification result from background thread.

        Call this after showing grading feedback to get detailed error info.
        Returns enriched grading if available, otherwise the base grading.
        """
        if self._error_future is None:
            return base_grading

        try:
            if self._error_future.done():
                detailed = self._error_future.result()
                self._error_future = None
                logger.info(f"Error classification collected: {detailed.error_category}")
                return detailed
        except Exception as e:
            logger.warning(f"Error classification failed: {e}")

        self._error_future = None
        return base_grading

    def handle_strategy_requested(
        self,
        mastery: MasteryState,
        syllabus: SyllabusOutput,
    ) -> str:
        """Generate a study strategy."""
        logger.info("Event: STRATEGY_REQUESTED")
        return run_study_strategy(mastery, syllabus)

    def get_srs_stats(self, session_id: str) -> dict:
        """Get SRS statistics for the sidebar display."""
        all_cards = self.db.get_all_cards(session_id)
        due_cards = self.db.get_due_cards(session_id)

        if not all_cards:
            return {"total_cards": 0, "due_cards": 0, "retention_rate": 0}

        # Retention rate = cards with repetitions > 0 / total cards
        learned = sum(1 for c in all_cards if c["repetitions"] > 0)
        retention = round(learned / len(all_cards) * 100) if all_cards else 0

        return {
            "total_cards": len(all_cards),
            "due_cards": len(due_cards),
            "retention_rate": retention,
        }

    def list_sessions(self) -> list[dict]:
        """List all available sessions for the session picker."""
        return self.db.list_sessions()

    def delete_session(self, session_id: str):
        """Delete a session."""
        self.db.delete_session(session_id)
