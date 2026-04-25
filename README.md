# Certification Practice Mastery

A multi-agent system that turns any certification name into an adaptive practice session with spaced repetition. Enter an exam (e.g. *"AWS Solutions Architect Associate"*) and the system maps the syllabus, generates questions targeted at your weakest domains, grades answers, tracks pass probability in real time, and schedules concept reviews using SM-2.

## Features

- **Any cert** — enter any IT/professional certification; the syllabus is mapped automatically
- **Adaptive difficulty** — per-domain, driven by running performance
- **Real-time pass probability** — weighted across domains, updated after every answer
- **Error classification** — wrong answers tagged as conceptual, careless, guess, etc.
- **QA loop** — a reviewer agent validates every question before it's served (up to 3 retries)
- **Spaced repetition (SM-2)** — due concepts are woven back into practice every 5th question
- **Session persistence** — close the tab, resume later; SQLite-backed
- **Syllabus cache** — repeat certs load in <10ms with no LLM call
- **Pre-generation** — next question generates in the background during feedback

## Architecture

Event-driven orchestrator routes events through five agents. Inter-agent contracts are Pydantic models in `schemas.py`. Grading and next-question generation run in parallel via `ThreadPoolExecutor`.

```
 Streamlit UI  ──►  Orchestrator  ──►  Agents ──►  SQLite
                    (state machine,       │         (sessions,
                     parallel exec,       │          SRS cards,
                     cache + SRS          │          syllabus cache,
                     routing)             │          question history)
                                          ▼
                    ┌─ Syllabus Mapper ─── LLM (JSON)
                    ├─ Question Generator ─ LLM (JSON) ──► QA Reviewer (LLM)
                    ├─ Grader ──────────── deterministic + LLM (parallel)
                    ├─ Mastery Scorer ──── deterministic
                    └─ Study Strategy ──── LLM (text)
```

### Agents

| # | Agent | Type | Purpose |
|---|---|---|---|
| 1 | Syllabus Mapper | LLM (JSON) | Cert name → structured syllabus (domains, weights, topics) |
| 2 | Question Generator | LLM (JSON) | One adaptive MCQ targeting weakest domain or SRS-due concept |
| 2b | QA Reviewer | LLM (JSON) | Validates question accuracy; triggers retry if rejected |
| 3 | Grader | Hybrid | Instant correctness check + LLM error classification on wrong answers only |
| 4 | Mastery Scorer | Deterministic | Updates domain scores, pass probability, SRS cards |
| 5 | Study Strategy | LLM (text) | Personalised study plan from session data |

## Getting started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An [OpenRouter](https://openrouter.ai/) API key

### Install

```bash
git clone https://github.com/0xKanu/certification-practice-mastery.git
cd certification-practice-mastery
uv sync   # or: pip install -e .
```

### Configure

```bash
cp .env.example .env
```

Then set in `.env`:

```
OPENROUTER_API_KEY=sk-or-v1-...
MODEL=meta-llama/llama-3.3-70b-instruct
```

Any OpenRouter-supported model works (GPT-4o, Claude, Gemini, Mistral, …) — change `MODEL` only.

### Run

```bash
uv run streamlit run app.py
```

Opens at `http://localhost:8501`.

## Testing

```bash
# Unit tests (53 tests, no API key)
uv run pytest tests/ -v --ignore=tests/test_pipeline.py

# End-to-end integration test (requires API key)
uv run python tests/test_pipeline.py
```

Unit tests cover the SQLite layer, SM-2 algorithm, JSON parsing, mastery scoring, and orchestrator routing. The integration test exercises the full 8-stage pipeline.

## Project structure

```
app.py              Streamlit UI — thin layer over the orchestrator
orchestrator.py     Event-driven routing, parallel agent execution
database.py         SQLite persistence (sessions, SRS, cache, history)
srs.py              SM-2 algorithm (~50 lines, stdlib only)
config.py           LLM client, call_llm / call_llm_json helpers
schemas.py          Pydantic contracts between agents
agents/             Five agent implementations
prompts/            Prompts as markdown files, separated from code
tests/              Unit + integration tests
```

## Tech stack

Streamlit · SQLite (stdlib) · Pydantic v2 · OpenRouter (OpenAI SDK) · uv · Python 3.11+

Default model: Meta Llama 3.3 70B Instruct.

## License

See `LICENSE`.
