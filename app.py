import streamlit as st
import json
from pydantic import ValidationError
from schemas import MasteryState, SyllabusOutput, AppStage
from agents.syllabus_mapper import run_syllabus_mapper
from agents.question_generator import run_question_generator
from agents.grader import run_grader
from agents.mastery_scorer import run_mastery_scorer
from agents.study_strategy import run_study_strategy


st.set_page_config(page_title="Cert Practice Mastery", layout="wide")

# ── Session state ─────────────────────────────────────────────
if "stage" not in st.session_state:
    st.session_state.stage = AppStage.SETUP
    st.session_state.syllabus = None
    st.session_state.mastery = MasteryState()
    st.session_state.current_question = None
    st.session_state.question_number = 0
    st.session_state.last_grading = None
    st.session_state.show_explanation = False

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

        # Strategy button
        st.divider()
        if st.button("Get study strategy"):
            with st.spinner("Analysing your session..."):
                strategy = run_study_strategy(m, st.session_state.syllabus)
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

        cert = st.text_input(
            "Certification",
            placeholder="e.g. Google Professional Data Engineer",
        )

        if st.button("Start practising", type="primary", disabled=not cert):
            with st.spinner("Mapping exam syllabus..."):
                try:
                    syllabus = run_syllabus_mapper(cert)
                    st.session_state.syllabus = syllabus
                    st.session_state.mastery = MasteryState()

                    # Initialise domain scores for all domains
                    from schemas import DomainScore
                    for d in syllabus.domains:
                        st.session_state.mastery.domain_scores[d.domain_name] = DomainScore()

                    st.session_state.stage = AppStage.GENERATING
                    st.rerun()
                except (json.JSONDecodeError, ValidationError) as e:
                    st.error(f"Failed to map syllabus due to an AI response error. Please try again. ({e})")
                except Exception as e:
                    st.error(f"Failed to map syllabus: {e}")

    # ── GENERATING QUESTION ───────────────────────────────────
    elif st.session_state.stage == AppStage.GENERATING:
        with st.spinner("Generating question..."):
            try:
                st.session_state.question_number += 1
                q = run_question_generator(
                    st.session_state.syllabus,
                    st.session_state.mastery,
                    st.session_state.question_number,
                )
                st.session_state.current_question = q
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

        # Show previous grading result if exists
        g = st.session_state.last_grading
        if g:
            if g.is_correct:
                st.success(f"Correct! {g.explanation}")
            else:
                st.error(
                    f"Incorrect — the answer was {g.correct_answer}. "
                    f"{g.explanation}"
                )
                if g.concept_gap:
                    st.caption(f"Gap identified: {g.concept_gap}")

        st.divider()

        # Question display
        header_cols = st.columns([3, 1, 1])
        header_cols[0].markdown(f"**Question {st.session_state.question_number}**")
        header_cols[1].caption(q.domain)
        header_cols[2].caption(q.difficulty)

        st.markdown(q.question_text)

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
            with st.spinner("Grading..."):
                try:
                    grading = run_grader(q, choice)
                    mastery = run_mastery_scorer(
                        st.session_state.mastery, grading, st.session_state.syllabus
                    )
                    st.session_state.mastery = mastery
                    st.session_state.last_grading = grading
                    st.session_state.stage = AppStage.GENERATING
                    st.rerun()
                except (json.JSONDecodeError, ValidationError) as e:
                    st.error(f"Grading failed due to an AI response error. ({e})")
                except Exception as e:
                    st.error(f"Grading failed: {e}")

        if col_skip.button("Skip"):
            st.session_state.stage = AppStage.GENERATING
            st.rerun()