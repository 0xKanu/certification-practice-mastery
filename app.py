import streamlit as st
import json
from pydantic import ValidationError
from schemas import MasteryState, SyllabusOutput, AppStage
from database import Database
from orchestrator import Orchestrator
from config import get_logger

logger = get_logger("App")

st.set_page_config(page_title="Cert Practice Mastery", layout="wide")

# ── Sidebar: Syllabus Cache Manager ───────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Syllabus Cache")
    st.caption("Manage cached exam syllabi. Delete entries that look wrong — the system will re-fetch from the web on your next session.")

    _db = Database()
    cached = _db.list_cached_syllabi()

    if not cached:
        st.info("No cached syllabi yet.")
    else:
        for entry in cached:
            with st.expander(f"📄 {entry['official_name']}", expanded=False):
                for d in entry["domains"]:
                    st.markdown(f"- {d}")
                st.caption(f"Cached: {entry['cached_at'][:10]}")
                if st.button("🗑️ Delete this", key=f"del_cache_{entry['cert_key']}"):
                    _db.delete_cached_syllabus(entry["cert_key"])
                    st.toast(f"Deleted: {entry['official_name']}", icon="🗑️")
                    st.rerun()

        st.divider()
        if st.button("🧹 Clear ALL cached syllabi", type="secondary"):
            count = _db.clear_all_cached_syllabi()
            st.toast(f"Cleared {count} cached syllabi!", icon="🧹")
            st.rerun()

# ── Persistent singletons ─────────────────────────────────────
@st.cache_resource
def get_db():
    return Database()

@st.cache_resource
def get_orchestrator():
    return Orchestrator(get_db())

orch = get_orchestrator()

# ── Session state ─────────────────────────────────────────────
if "stage" not in st.session_state:
    st.session_state.stage = AppStage.SETUP
    st.session_state.syllabus = None
    st.session_state.mastery = MasteryState()
    st.session_state.current_question = None
    st.session_state.question_number = 0
    st.session_state.last_grading = None
    st.session_state.show_explanation = False
    st.session_state.cert_name = ""

left, right = st.columns([2, 1])


# ── Right panel: live dashboard ───────────────────────────────
with right:
    if st.session_state.stage == AppStage.PRACTISING:
        m = st.session_state.mastery

        st.markdown(f"### {st.session_state.syllabus.certification.official_name}")

        # Pass probability gauge
        st.metric("Pass probability", f"{m.pass_probability}%")

        total = m.total_questions
        correct = m.total_correct
        accuracy = round(correct / total * 100) if total > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Answered", total)
        c2.metric("Correct", correct)
        c3.metric("Accuracy", f"{accuracy}%")

        # Streak indicator
        if m.current_streak >= 3:
            st.success(f"🔥 {m.current_streak} streak!")
        elif m.current_streak > 0:
            st.caption(f"Streak: {m.current_streak}")

        # Domain mastery bars
        st.divider()
        st.markdown("**Domain mastery**")
        for d in st.session_state.syllabus.domains:
            score = m.domain_scores.get(d.domain_name)
            pct = score.mastery_percent if score and score.attempted > 0 else 0
            attempted = score.attempted if score else 0
            st.progress(pct / 100, text=f"{d.domain_name}: {pct}% ({attempted} Qs)")

        # Weakest domain callout
        if m.weakest_domain:
            st.divider()
            ws = m.domain_scores[m.weakest_domain]
            st.caption(f"Focus area: **{m.weakest_domain}** ({ws.mastery_percent}%)")

        # ── SRS Stats ─────────────────────────────────────────
        if m.session_id:
            srs_stats = orch.get_srs_stats(m.session_id)
            if srs_stats["total_cards"] > 0:
                st.divider()
                st.markdown("**Spaced Repetition**")
                s1, s2 = st.columns(2)
                s1.metric("Concepts", srs_stats["total_cards"])
                s2.metric("Due for review", srs_stats["due_cards"])
                st.progress(
                    srs_stats["retention_rate"] / 100,
                    text=f"Retention: {srs_stats['retention_rate']}%"
                )
                if m.srs_review_count > 0:
                    st.caption(f"Reviews this session: {m.srs_review_count}")

        # Strategy button
        st.divider()
        if st.button("Get study strategy"):
            logger.info("User requested a study strategy.")
            with st.spinner("Analysing your session..."):
                strategy = orch.handle_strategy_requested(m, st.session_state.syllabus)
            st.markdown(strategy)


# ── Left panel: practice interface ────────────────────────────
with left:

    # ── SETUP ─────────────────────────────────────────────────
    if st.session_state.stage == AppStage.SETUP:
        st.title("Certification Practice Mastery")
        st.markdown(
            "Enter a certification name to start an adaptive practice session. "
            "The system maps the exam syllabus, generates targeted questions, "
            "and tracks your pass probability in real time."
        )

        # ── Session Picker (resume past sessions) ─────────────
        sessions = orch.list_sessions()
        if sessions:
            st.markdown("#### Resume a session")
            for s in sessions[:5]:  # Show last 5
                col_info, col_resume, col_delete = st.columns([4, 1, 1])
                with col_info:
                    st.markdown(
                        f"**{s['cert_name']}** — "
                        f"{s['question_count']} Qs, "
                        f"{s['pass_probability']}% pass"
                    )
                with col_resume:
                    if st.button("Resume", key=f"resume_{s['session_id']}"):
                        logger.info(f"User resuming session {s['session_id']}")
                        result = orch.handle_session_resume(s["session_id"])
                        if result:
                            st.session_state.syllabus = result["syllabus"]
                            st.session_state.mastery = result["mastery"]
                            st.session_state.cert_name = result["cert_name"]
                            st.session_state.question_number = result["mastery"].total_questions
                            st.session_state.stage = AppStage.GENERATING
                            st.rerun()
                with col_delete:
                    if st.button("🗑️", key=f"del_{s['session_id']}"):
                        orch.delete_session(s["session_id"])
                        st.rerun()

            st.divider()
            st.markdown("#### Or start a new session")

        cert = st.text_input(
            "Certification",
            placeholder="e.g. Google Professional Data Engineer",
        )

        if st.button("Start practising", type="primary", disabled=not cert):
            logger.info(f"User started session for cert: '{cert}'")
            with st.spinner("Mapping exam syllabus..."):
                try:
                    result = orch.handle_cert_submitted(cert)
                    syllabus = result["syllabus"]

                    if result["cached"]:
                        st.toast("Loaded from cache — instant!", icon="⚡")

                    if not syllabus.is_valid:
                        st.error(syllabus.error_message or "Invalid certification. Please try again.")
                    else:
                        st.session_state.syllabus = syllabus
                        st.session_state.cert_name = cert
                        st.session_state.stage = AppStage.SYLLABUS_REVIEW
                        st.rerun()
                except (json.JSONDecodeError, ValidationError) as e:
                    st.error(f"Failed to map syllabus due to an AI response error. Please try again. ({e})")
                except Exception as e:
                    st.error(f"Failed to map syllabus: {e}")

    # ── SYLLABUS REVIEW ───────────────────────────────────────
    elif st.session_state.stage == AppStage.SYLLABUS_REVIEW:
        st.title("Exam Syllabus")
        s = st.session_state.syllabus

        st.markdown(f"### {s.certification.official_name}")
        st.markdown(f"**Provider:** {s.certification.provider}")
        if s.notes:
            st.info(s.notes)

        for d in s.domains:
            with st.expander(f"{d.domain_name} ({d.weight_percent}%)", expanded=True):
                st.markdown("**Key Topics:**")
                for topic in d.key_topics:
                    st.markdown(f"- {topic}")

        st.divider()
        col1, col2 = st.columns([1, 1])

        if col1.button("✅ Looks good, let's start!", type="primary"):
            logger.info("User accepted syllabus, starting practice.")

            # Create session via orchestrator
            result = orch.handle_session_start(
                st.session_state.cert_name,
                st.session_state.syllabus,
            )
            st.session_state.mastery = result["mastery"]

            st.session_state.stage = AppStage.GENERATING
            st.rerun()

        if col2.button("❌ No, wrong cert (Go Back)"):
            logger.info("User rejected syllabus, returning to setup.")
            st.session_state.stage = AppStage.SETUP
            st.session_state.syllabus = None
            st.rerun()

    # ── GENERATING QUESTION ───────────────────────────────────
    elif st.session_state.stage == AppStage.GENERATING:
        with st.spinner("Generating question..."):
            try:
                st.session_state.question_number += 1
                q = orch.handle_generate_question(
                    st.session_state.syllabus,
                    st.session_state.mastery,
                    st.session_state.question_number,
                )
                st.session_state.current_question = q

                # Track recent questions to prevent repeats (keep last 15)
                st.session_state.mastery.recent_questions.append(q.question_text)
                if len(st.session_state.mastery.recent_questions) > 15:
                    st.session_state.mastery.recent_questions.pop(0)

                st.session_state.last_grading = None
                st.session_state.show_explanation = False
                st.session_state.stage = AppStage.PRACTISING
                st.rerun()
            except (json.JSONDecodeError, ValidationError) as e:
                st.error(f"Failed to generate question due to an AI response error. ({e})")
                st.session_state.stage = AppStage.PRACTISING
            except Exception as e:
                st.error(f"Failed to generate question: {e}")
                st.session_state.stage = AppStage.PRACTISING

    # ── PRACTISING ────────────────────────────────────────────
    elif st.session_state.stage == AppStage.PRACTISING:
        q = st.session_state.current_question

        if q is None:
            st.session_state.stage = AppStage.GENERATING
            st.rerun()

        # Show grading feedback
        g = st.session_state.last_grading
        if g:
            # Try to collect error classification from background
            g = orch.collect_error_classification(g)
            st.session_state.last_grading = g

            if g.is_correct:
                st.success(f"✅ Correct! {g.explanation}")
            else:
                st.error(
                    f"❌ Incorrect — the answer was **{g.correct_answer}**. "
                    f"{g.explanation}"
                )
                # Explain WHY the answer was wrong
                if g.error_reasoning:
                    st.caption(f"💡 Why it's wrong: {g.error_reasoning}")
                if g.error_category:
                    category_labels = {
                        "conceptual_misunderstanding": "🧠 Conceptual gap",
                        "incomplete_knowledge": "📚 Knowledge gap",
                        "misread_question": "👀 Misread question",
                        "careless_error": "⚡ Careless error",
                        "random_guess": "🎲 Random guess",
                    }
                    cat_value = g.error_category.value if hasattr(g.error_category, 'value') else g.error_category
                    label = category_labels.get(cat_value, cat_value)
                    st.caption(f"Error type: {label}")
                if g.concept_gap:
                    st.caption(f"Gap identified: {g.concept_gap}")

            # Continue button to proceed to next question (while prefetch runs in background)
            st.divider()
            if st.button("Continue to next question", type="primary"):
                    # Try to get prefetched question (instant if ready)
                    prefetched = orch.get_prefetched_question()
                    if prefetched:
                        st.session_state.current_question = prefetched
                        st.session_state.question_number += 1
                        # Track recent questions
                        st.session_state.mastery.recent_questions.append(prefetched.question_text)
                        if len(st.session_state.mastery.recent_questions) > 15:
                            st.session_state.mastery.recent_questions.pop(0)
                        st.session_state.last_grading = None
                        st.session_state.show_explanation = False
                        st.toast("⚡ Next question ready!", icon="⚡")
                        st.rerun()
                    else:
                        st.session_state.stage = AppStage.GENERATING
                        st.rerun()

        st.divider()

        # Show question display
        header_cols = st.columns([3, 1, 1])
        header_cols[0].markdown(f"**Question {st.session_state.question_number}**")
        header_cols[1].caption(q.domain)
        header_cols[2].caption(q.difficulty)

        st.markdown(q.question_text)

        # Only show answer interface if NO grading yet (prevents re-answering)
        if not st.session_state.last_grading:
            # Answer options
            options = {opt.label: opt.text for opt in q.options}
            choice = st.radio(
                "Your answer",
                options=list(options.keys()),
                format_func=lambda x: f"{x}) {options[x]}",
                label_visibility="collapsed",
            )

            col_submit, col_skip = st.columns([1, 1])

            if col_submit.button("Submit answer", type="primary"):
                logger.info(f"User submitted answer: '{choice}'")
                # Use orchestrator for parallel grading + pre-generation
                try:
                    result = orch.handle_answer_submitted(
                        question=q,
                        student_answer=choice,
                        syllabus=st.session_state.syllabus,
                        mastery=st.session_state.mastery,
                        question_number=st.session_state.question_number,
                    )
                    st.session_state.mastery = result["mastery"]
                    st.session_state.last_grading = result["grading"]
                    # Don't change stage - keep showing grading while prefetch runs in background
                    st.rerun()
                except (json.JSONDecodeError, ValidationError) as e:
                    st.error(f"Grading failed due to an AI response error. ({e})")
                except Exception as e:
                    st.error(f"Grading failed: {e}")

            if col_skip.button("Skip"):
                logger.info("User skipped the question.")
                # Try to get prefetched question before generating new one
                prefetched = orch.get_prefetched_question()
                if prefetched:
                    st.session_state.current_question = prefetched
                    st.session_state.question_number += 1
                    st.session_state.mastery.recent_questions.append(prefetched.question_text)
                    if len(st.session_state.mastery.recent_questions) > 15:
                        st.session_state.mastery.recent_questions.pop(0)
                    st.session_state.last_grading = None
                    st.session_state.show_explanation = False
                    st.rerun()
                else:
                    st.session_state.stage = AppStage.GENERATING
                    st.rerun()