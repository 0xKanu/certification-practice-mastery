from pydantic import BaseModel, Field
from enum import Enum


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AppStage(str, Enum):
    SETUP = "setup"
    GENERATING = "generating"
    PRACTISING = "practising"


class Domain(BaseModel):
    domain_name: str
    weight_percent: int
    key_topics: list[str]
    subtopics: list[str]
    confidence: Confidence


class CertificationMeta(BaseModel):
    official_name: str
    provider: str
    exam_code: str | None = None
    passing_score: str | None = None
    total_questions: int | None = None
    time_limit_minutes: int | None = None
    question_format: str | None = None


class SyllabusOutput(BaseModel):
    certification: CertificationMeta
    domains: list[Domain]
    notes: str | None = None
    confidence_overall: Confidence


class Option(BaseModel):
    label: str
    text: str


class QuestionOutput(BaseModel):
    question_id: str
    domain: str
    subtopic: str
    difficulty: str
    question_text: str
    options: list[Option]
    correct_answer: str
    explanation: str
    concept_tested: str


class ErrorCategory(str, Enum):
    CONCEPTUAL = "conceptual_misunderstanding"
    INCOMPLETE = "incomplete_knowledge"
    MISREAD = "misread_question"
    CARELESS = "careless_error"
    GUESS = "random_guess"


class GradingOutput(BaseModel):
    question_id: str
    domain: str
    subtopic: str
    is_correct: bool
    student_answer: str
    correct_answer: str
    error_category: ErrorCategory | None = None
    error_reasoning: str | None = None
    explanation: str
    concept_gap: str | None = None


class DomainScore(BaseModel):
    mastery_percent: int = 50
    correct: int = 0
    attempted: int = 0
    recent: list[bool] = Field(default_factory=list)
    difficulty_trend: str = "stable"


class MasteryState(BaseModel):
    pass_probability: int = 0
    domain_scores: dict[str, DomainScore] = Field(default_factory=dict)
    total_questions: int = 0
    total_correct: int = 0
    current_streak: int = 0
    weakest_domain: str | None = None