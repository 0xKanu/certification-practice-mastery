# 🎓 Certification Practice Mastery

> **A multi-agent AI system that turns any certification exam name into an adaptive, real-time practice session.**

Type in a certification (e.g. *"AWS Solutions Architect Associate"*), and the system autonomously maps the exam syllabus, generates targeted questions calibrated to your weak spots, grades your answers with error classification, and tracks your pass probability — all in real time.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **Universal Cert Support** | Enter *any* IT/professional certification — the AI maps the official syllabus automatically |
| **Adaptive Difficulty** | Questions get harder as you improve and easier when you struggle, per domain |
| **Real-Time Pass Probability** | Weighted scoring across all exam domains, updated after every answer |
| **Error Classification** | Every wrong answer is categorised (conceptual gap, careless error, knowledge gap, etc.) |
| **QA Review Loop** | A dedicated reviewer agent validates every generated question for factual accuracy before you see it |
| **Study Strategy** | On-demand, personalised study plan based on your actual session performance |
| **Syllabus Preview** | Review the mapped exam syllabus before starting — reject and retry if it's wrong |
| **No Question Repeats** | Rolling history window prevents the system from re-asking the same concepts |

---

## 🏗️ Architecture

The system is built as a **multi-agent pipeline** where each agent has a single responsibility. Agents communicate through structured Pydantic schemas, ensuring type safety at every boundary.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          STREAMLIT UI (app.py)                         │
│                                                                        │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐ │
│   │  SETUP   │───▶│ SYLLABUS │───▶│GENERATING│───▶│   PRACTISING    │ │
│   │  Stage   │    │  REVIEW  │    │  Stage   │◀───│     Stage       │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────────────┘ │
└────────┬──────────────────────────────┬───────────────────┬────────────┘
         │                              │                   │
         ▼                              ▼                   ▼
┌─────────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
│ Agent 1:        │  │ Agent 2:                 │  │ Agent 3:         │
│ Syllabus Mapper │  │ Question Generator       │  │ Grader           │
│                 │  │         │                │  │                  │
│ cert name ──▶   │  │         ▼                │  │ question +       │
│ structured      │  │ ┌─────────────────────┐  │  │ answer ──▶       │
│ syllabus JSON   │  │ │ Agent 2b:           │  │  │ grading +        │
│                 │  │ │ QA Reviewer         │  │  │ error class.     │
│                 │  │ │ (approve/retry ×3)  │  │  │                  │
└─────────────────┘  │ └─────────────────────┘  │  └────────┬─────────┘
                     └──────────────────────────┘           │
                                                            ▼
                                                 ┌──────────────────┐
                                                 │ Agent 4:         │
                                                 │ Mastery Scorer   │
                                                 │ (deterministic)  │
                                                 │                  │
                                                 │ updates domain   │
                                                 │ scores, pass %,  │
                                                 │ difficulty trend  │
                                                 └────────┬─────────┘
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │ Agent 5:         │
                                                 │ Study Strategy   │
                                                 │ (on-demand)      │
                                                 │                  │
                                                 │ personalised     │
                                                 │ study plan       │
                                                 └──────────────────┘
```

### Agent Breakdown

| # | Agent | Type | Purpose |
|---|-------|------|---------|
| 1 | **Syllabus Mapper** | LLM (JSON) | Converts a certification name into a structured syllabus with domains, weights, topics, and metadata |
| 2 | **Question Generator** | LLM (JSON) | Generates one adaptive multiple-choice question targeting the weakest domain |
| 2b | **QA Reviewer** | LLM (JSON) | Validates generated questions for factual accuracy; triggers up to 3 retries if rejected |
| 3 | **Grader** | LLM (JSON) | Grades the student's answer, classifies error type, and identifies concept gaps |
| 4 | **Mastery Scorer** | Deterministic | Pure arithmetic — updates domain scores, pass probability, difficulty trends. No LLM call. |
| 5 | **Study Strategy** | LLM (text) | Analyses full session data and generates actionable study recommendations |

### Data Flow

All inter-agent communication uses **Pydantic models** defined in `schemas.py`:

- `SyllabusOutput` — structured exam breakdown (domains, weights, topics, confidence levels)
- `QuestionOutput` — single multiple-choice question with metadata
- `QAReviewOutput` — approve/reject decision from the reviewer
- `GradingOutput` — correctness, error classification, explanation, concept gap
- `MasteryState` — running session state (domain scores, pass probability, streaks)

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- An **[OpenRouter](https://openrouter.ai/)** API key

### Installation

```bash
# Clone the repository
git clone https://github.com/0xKanu/certification-practice-mastery.git
cd certification-practice-mastery

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .
```

### Configuration

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your API key:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
MODEL=meta-llama/llama-3.3-70b-instruct
```

> **Model flexibility:** The system uses [OpenRouter](https://openrouter.ai/) as the LLM gateway. Change the `MODEL` variable to use any supported model (GPT-4o, Claude, Gemini, Mistral, etc.) — no code changes required.

### Run the App

```bash
uv run streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## 🎮 How to Use

1. **Enter a certification name** — e.g. *"AWS Solutions Architect Associate"*, *"Google Professional Data Engineer"*, or *"CompTIA Security+"*
2. **Review the syllabus** — the system maps the exam domains, weights, and key topics. Accept it or go back to try a different cert.
3. **Answer questions** — adaptive multiple-choice questions appear one at a time, targeted at your weakest domain
4. **Track your progress** — the right panel shows real-time pass probability, accuracy, and per-domain mastery bars
5. **Get a study strategy** — click "Get study strategy" at any time for a personalised action plan based on your session data

---

## 🧪 Testing

The project includes both unit tests and an end-to-end pipeline integration test.

```bash
# Run unit tests (no API key needed)
uv run pytest tests/test_config.py tests/test_mastery_scorer.py -v

# Run full pipeline integration test (requires API key)
uv run python tests/test_pipeline.py
```

**Unit tests cover:**
- JSON markdown stripping in `call_llm_json` (handles ```json blocks)
- Mastery scorer arithmetic (domain scores, pass probability, streak tracking, difficulty trends)

**Integration test covers:**
- Full 6-stage pipeline: Syllabus Mapping → Question Generation → Grading (correct) → Grading (wrong) → Mastery Scoring → Study Strategy

---

## 📁 Project Structure

```
certification-practice-mastery/
├── app.py                  # Streamlit UI — session management, layout, user interactions
├── config.py               # LLM client setup, call_llm / call_llm_json helpers, logging
├── schemas.py              # All Pydantic models (data contracts between agents)
│
├── agents/                 # Multi-agent implementations
│   ├── syllabus_mapper.py  # Agent 1: cert name → structured syllabus
│   ├── question_generator.py # Agent 2: syllabus + mastery → adaptive question (with QA loop)
│   ├── qa_reviewer.py      # Agent 2b: validates question quality, approve/reject
│   ├── grader.py           # Agent 3: question + answer → grading + error classification
│   ├── mastery_scorer.py   # Agent 4: deterministic mastery state updates (no LLM)
│   └── study_strategy.py   # Agent 5: mastery state → personalised study plan
│
├── prompts/                # Markdown prompt files (separated from code for easy iteration)
│   ├── syllabus_mapper.md
│   ├── question_generator.md
│   ├── qa_reviewer.md
│   ├── grader.md
│   └── study_strategy.md
│
├── tests/                  # Test suite
│   ├── test_config.py      # Unit tests for JSON parsing
│   ├── test_mastery_scorer.py # Unit tests for scoring logic
│   └── test_pipeline.py    # End-to-end integration test
│
├── pyproject.toml          # Project metadata and dependencies
├── .env.example            # Template for environment variables
└── .python-version         # Python version pin (3.11)
```

---

## 🔧 Technical Decisions

| Decision | Rationale |
|---|---|
| **Prompts as Markdown files** | Separated from Python code for easy iteration, review, and versioning without touching agent logic |
| **OpenRouter gateway** | Single API key gives access to 100+ models; swap models via env var without code changes |
| **Pydantic schemas everywhere** | Type-safe contracts between agents; automatic validation catches LLM output errors early |
| **Deterministic mastery scorer** | No LLM call for scoring — faster, free, reproducible, and testable |
| **QA reviewer with retry loop** | Self-correcting pipeline: if a generated question has factual errors, the system catches and fixes it before the user sees it (up to 3 attempts) |
| **Rolling question history** | Keeps last 15 questions in state to prevent the LLM from repeating concepts |
| **Syllabus review stage** | User transparency — verify the AI's exam breakdown before starting practice |

---

## 🛠️ Tech Stack

- **Frontend:** [Streamlit](https://streamlit.io/)
- **LLM Gateway:** [OpenRouter](https://openrouter.ai/) (OpenAI SDK compatible)
- **Default Model:** Meta Llama 3.3 70B Instruct
- **Data Validation:** [Pydantic v2](https://docs.pydantic.dev/)
- **Package Management:** [uv](https://docs.astral.sh/uv/)
- **Language:** Python 3.11+

---

## 📄 License

This project is open source. See `LICENSE` for details.

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/0xKanu">0xKanu</a>
</p>
