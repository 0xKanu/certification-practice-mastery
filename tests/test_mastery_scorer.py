from schemas import MasteryState, DomainScore, SyllabusOutput, CertificationMeta, Domain, GradingOutput
from agents.mastery_scorer import run_mastery_scorer

def test_run_mastery_scorer():
    # Setup
    syllabus = SyllabusOutput(
        certification=CertificationMeta(official_name="Test Cert", provider="Test"),
        domains=[
            Domain(domain_name="D1", weight_percent=60, key_topics=[], subtopics=[], confidence="high"),
            Domain(domain_name="D2", weight_percent=40, key_topics=[], subtopics=[], confidence="high"),
        ],
        confidence_overall="high"
    )
    
    state = MasteryState()
    
    # Test correct grading
    grading_correct = GradingOutput(
        question_id="1", domain="D1", subtopic="", is_correct=True,
        student_answer="A", correct_answer="A", explanation="test"
    )
    
    state = run_mastery_scorer(state, grading_correct, syllabus)
    assert state.total_questions == 1
    assert state.total_correct == 1
    assert state.current_streak == 1
    assert state.domain_scores["D1"].attempted == 1
    assert state.domain_scores["D1"].correct == 1
    
    # Mastery doesn't update until 3 questions, defaults to 50
    assert state.domain_scores["D1"].mastery_percent == 50
    
    # Test incorrect grading
    grading_wrong = GradingOutput(
        question_id="2", domain="D1", subtopic="", is_correct=False,
        student_answer="B", correct_answer="A", explanation="test",
        error_category="conceptual_misunderstanding"
    )
    
    state = run_mastery_scorer(state, grading_wrong, syllabus)
    assert state.total_questions == 2
    assert state.total_correct == 1
    assert state.current_streak == 0
    assert state.domain_scores["D1"].attempted == 2
    assert state.domain_scores["D1"].correct == 1
    
    # Add a third question to trigger mastery calculation
    state = run_mastery_scorer(state, grading_correct, syllabus)
    assert state.domain_scores["D1"].attempted == 3
    # 2 correct out of 3 = 67%
    assert state.domain_scores["D1"].mastery_percent == 67
    
    # Verify overall pass probability. 
    # D1 is tested (67%), D2 is not (defaults to 50%).
    # Total weighted: (0.6 * 0.67) + (0.4 * 0.5) = 0.402 + 0.2 = 0.602 -> 60%
    assert state.pass_probability == 60
    
    # Verify weakest domain
    assert state.weakest_domain == "D1"  # Only tested domains are considered
