# 🎓 Certification Practice Mastery

> **A multi-agent AI system that turns any certification exam name into an adaptive, real-time practice session with spaced repetition.**

Type in a certification (e.g. *"AWS Solutions Architect Associate"*), and the system autonomously maps the exam syllabus, generates targeted questions calibrated to your weak spots, grades your answers with error classification, tracks your pass probability, and schedules concept reviews using the SM-2 spaced repetition algorithm — all in real time.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **Universal Cert Support** | Enter *any* IT/professional certification — the AI maps the official syllabus automatically |
| **Adaptive Difficulty** | Questions get harder as you improve and easier when you struggle, per domain |
| **Real-Time Pass Probability** | Weighted scoring across all exam domains, updated after every answer |
| **Error Classification** | Every wrong answer is categorised (conceptual gap, careless error, knowledge gap, etc.) |
| **QA Review Loop** | A dedicated reviewer agent validates every generated question for factual accuracy before you see it |
| **Spaced Repetition (SM-2)** | Anki-style algorithm tracks concept retention — review questions are woven into practice automatically |
| **Study Strategy** | On-demand, personalised study plan based on your actual session performance |
| **Session Persistence** | SQLite-backed sessions — close the tab, come back later, pick up where you left off |
| **Syllabus Caching** | Repeat certs load instantly from cache (no LLM call) |
| **Pre-Generation Pipeline** | Next question generates in the background while you read feedback — near-instant delivery |
| **No Question Repeats** | Rolling history window prevents the system from re-asking the same concepts |

---

## 🏗️ Architecture

The system is built as a **multi-agent pipeline** orchestrated by an **event-driven state machine**. The orchestrator makes routing decisions (cache hits, SRS scheduling, QA retry budgets) and runs agents in parallel for reduced latency. All inter-agent communication uses structured Pydantic schemas.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT UI (app.py)                            │
│  ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌───────────────────────┐ │
│  │   SETUP /  │  │ SYLLABUS │  │GENERATING │  │     PRACTISING        │ │
│  │  SESSION   │─▶│  REVIEW  │─▶│  (async)  │─▶│  (pre-gen in bg)     │ │
│  │  PICKER    │  │          │  │           │  │                       │ │
│  └────────────┘  └──────────┘  └───────────┘  └───────────────────────┘ │
└────────┬────────────────┬──────────────┬──────────────────┬─────────────┘
         │                │              │                  │
         ▼                ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (orchestrator.py)                        │
│                                                                         │
│  Events ──▶ Router ──▶ Actions                                          │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Event               │  Router Decision         │  Action       │    │
│  ├──────────────────────┼──────────────────────────┼───────────────┤    │
│  │ CERT_SUBMITTED       │ cached? → skip mapper    │ MAP / CACHE   │    │
│  │ SYLLABUS_ACCEPTED    │ always                   │ CREATE SESSION│    │
│  │ QUESTION_NEEDED      │ prefetched? SRS due?     │ SERVE / GEN   │    │
│  │ QA_APPROVED          │ always                   │ SERVE         │    │
│  │ QA_REJECTED          │ retries < 3?             │ REGEN / SERVE │    │
│  │ ANSWER_SUBMITTED     │ always (PARALLEL)        │ GRADE + GEN   │    │
│  │ GRADING_COMPLETE     │ SRS due? (every 5th Q)   │ SRS_REVIEW    │    │
│  │ STRATEGY_REQUESTED   │ always                   │ STRATEGIZE    │    │
│  └──────────────────────┴──────────────────────────┴───────────────┘    │
│                                                                         │
│  Parallel Executor: grade_current + generate_next run simultaneously    │
└────────┬────────┬───────────┬────────────┬────────────┬─────────────────┘
         │        │           │            │            │
         ▼        ▼           ▼            ▼            ▼
┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Syllabus│ │ Question │ │  Grader  │ │ Mastery  │ │  Study   │
│ Mapper │ │Generator │ │(hybrid)  │ │ Scorer   │ │ Strategy │
│        │ │+ QA Loop │ │det+LLM   │ │ + SRS    │ │          │
└────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │   SQLite DB   │
                                   │  • sessions   │
                                   │  • srs_cards  │
                                   │  • syllabus   │
                                   │    cache      │
                                   │  • question   │
                                   │    history    │
                                   └──────────────┘
```

### Agent Breakdown

| # | Agent | Type | Purpose |
|---|-------|------|---------| 
| 1 | **Syllabus Mapper** | LLM (JSON) | Converts a certification name into a structured syllabus with domains, weights, topics, and metadata |
| 2 | **Question Generator** | LLM (JSON) | Generates one adaptive multiple-choice question targeting the weakest domain (or SRS review concept) |
| 2b | **QA Reviewer** | LLM (JSON) | Validates generated questions for factual accuracy; triggers up to 3 retries if rejected |
| 3 | **Grader** | Hybrid | Deterministic correctness check (instant) + LLM error classification (parallel, only for wrong answers) |
| 4 | **Mastery Scorer** | Deterministic | Pure arithmetic — updates domain scores, pass probability, difficulty trends, SRS cards. No LLM call. |
| 5 | **Study Strategy** | LLM (text) | Analyses full session data and generates actionable study recommendations |
| ★ | **Orchestrator** | State Machine | Event-driven routing — cache hits, parallel execution, SRS scheduling, pre-generation |

### Data Flow

All inter-agent communication uses **Pydantic models** defined in `schemas.py`:

- `SyllabusOutput` — structured exam breakdown (domains, weights, topics, confidence levels)
- `QuestionOutput` — single multiple-choice question with metadata
- `QAReviewOutput` — approve/reject decision from the reviewer
- `GradingOutput` — correctness, error classification, explanation, concept gap
- `MasteryState` — running session state (domain scores, pass probability, streaks, SRS flags)
- `SRSCard` — spaced repetition metadata (ease factor, interval, repetitions, next review)

### Latency Optimisation

Three strategies combine for **~70% perceived latency reduction**:

| Strategy | How | Impact |
|---|---|---|
| **Pre-Generation** | Next question generates in background while user reads feedback | 0-2s vs 5-15s |
| **Deterministic Grading** | Correctness is instant string comparison; LLM only called for error classification (and only when wrong) | Eliminates grading wait for correct answers |
| **Syllabus Caching** | SQLite cache means repeat certs load in <0.01s | Instant on repeat visits |

---

## 🧠 Spaced Repetition (SM-2)

The system implements the **SuperMemo-2 algorithm** — the same algorithm that powers Anki — for long-term concept retention.

**How it works:**
1. Every question tests a concept. After grading, an SRS card is created/updated for that concept.
2. The SM-2 algorithm calculates the next optimal review date based on how well you answered.
3. Every 5th question, the orchestrator checks for due SRS cards and weaves a review question into your practice session.
4. Concepts you get wrong are reviewed sooner; concepts you ace are spaced out further.

**Quality mapping from grading:**

| Grading Result | SM-2 Quality | Effect |
|---|---|---|
| Correct | 4 | Interval increases, ease stays stable |
| Wrong (careless / misread) | 2 | Interval resets, ease decreases slightly |
| Wrong (conceptual / incomplete) | 1 | Interval resets, ease decreases |
| Wrong (random guess) | 0 | Full reset, ease decreases significantly |

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
4. **Track your progress** — the right panel shows real-time pass probability, accuracy, per-domain mastery bars, and SRS retention stats
5. **Get a study strategy** — click "Get study strategy" at any time for a personalised action plan based on your session data
6. **Resume anytime** — close the tab and come back later. Your session picker shows all past sessions with their stats.

---

## 🧪 Testing

The project includes unit tests (53 tests), and an end-to-end pipeline integration test.

```bash
# Run unit tests (no API key needed — 53 tests)
uv run pytest tests/test_database.py tests/test_srs.py tests/test_config.py tests/test_mastery_scorer.py tests/test_orchestrator.py -v

# Run full pipeline integration test (requires API key)
uv run python tests/test_pipeline.py
```

**Unit tests cover:**
- SQLite persistence layer (CRUD, cache normalisation, SRS card due filtering)
- SM-2 algorithm (interval progression, ease factor bounds, quality mapping)
- JSON markdown stripping in `call_llm_json`
- Mastery scorer arithmetic (domain scores, pass probability, streak tracking)
- Orchestrator routing (cache hits, parallel execution, SRS scheduling, session management)

**Integration test covers:**
- Full 8-stage pipeline through the orchestrator: Syllabus Mapping → Cache Hit → Session Creation → Question Generation → Correct Answer (parallel grading) → Wrong Answer (error classification) → SRS Card Creation → Study Strategy + Session Resume

---

## 📁 Project Structure

```
certification-practice-mastery/
├── app.py                  # Streamlit UI — thin layer, delegates to orchestrator
├── orchestrator.py         # Event-driven agent orchestrator (routing, parallel exec)
├── database.py             # SQLite persistence (sessions, SRS, cache, history)
├── srs.py                  # SM-2 spaced repetition algorithm
├── config.py               # LLM client setup, call_llm / call_llm_json helpers
├── schemas.py              # All Pydantic models (data contracts between agents)
│
├── agents/                 # Multi-agent implementations
│   ├── syllabus_mapper.py  # Agent 1: cert name → structured syllabus
│   ├── question_generator.py # Agent 2: syllabus + mastery → adaptive question (with QA loop)
│   ├── qa_reviewer.py      # Agent 2b: validates question quality, approve/reject
│   ├── grader.py           # Agent 3: deterministic check + LLM error classification
│   ├── mastery_scorer.py   # Agent 4: deterministic scoring + SRS card updates
│   └── study_strategy.py   # Agent 5: mastery state → personalised study plan
│
├── prompts/                # Markdown prompt files (separated from code)
│   ├── syllabus_mapper.md
│   ├── question_generator.md
│   ├── qa_reviewer.md
│   ├── grader.md
│   └── study_strategy.md
│
├── tests/                  # Test suite (53 unit + 1 integration)
│   ├── test_config.py      # Unit tests for JSON parsing
│   ├── test_database.py    # Unit tests for persistence layer
│   ├── test_srs.py         # Unit tests for SM-2 algorithm
│   ├── test_mastery_scorer.py # Unit tests for scoring logic
│   ├── test_orchestrator.py   # Unit tests for routing decisions
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
| **Event-driven orchestrator** | Makes routing decisions based on state (cache, SRS, retry budget) — genuinely agentic, not just a linear pipeline |
| **Parallel execution** | Error classification + next question generation run simultaneously via ThreadPoolExecutor, cutting perceived latency ~70% |
| **SM-2 spaced repetition** | Science-backed algorithm (same as Anki) for long-term retention, automatically woven into practice sessions |
| **Deterministic grading split** | Correctness is instant (string comparison); LLM only called for error classification on wrong answers |
| **SQLite persistence** | Zero-dependency session storage, syllabus caching, SRS cards, and question history |
| **Prompts as Markdown files** | Separated from Python code for easy iteration, review, and versioning |
| **OpenRouter gateway** | Single API key gives access to 100+ models; swap models via env var |
| **Pydantic schemas everywhere** | Type-safe contracts between agents; automatic validation catches LLM output errors early |
| **QA reviewer with retry loop** | Self-correcting pipeline: generated questions validated for accuracy before serving (up to 3 attempts) |
| **Pre-generation pipeline** | Next question cooks in background while user reads feedback — near-instant delivery |
| **Zero new dependencies** | SQLite, threading, and SM-2 are all stdlib/hand-rolled — lean and impressive |

---

## 🛠️ Tech Stack

- **Frontend:** [Streamlit](https://streamlit.io/)
- **Orchestration:** Custom event-driven state machine with parallel execution
- **Persistence:** SQLite (stdlib)
- **Spaced Repetition:** SM-2 algorithm (hand-rolled, ~50 lines)
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
