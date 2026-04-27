# AGENTS.md — Certification Practice Mastery

## Commands

```bash
# Unit tests (53 tests, no API key needed)
uv run pytest tests/ -v --ignore=tests/test_pipeline.py

# Integration test (requires OPENROUTER_API_KEY in .env)
uv run python tests/test_pipeline.py

# Run the app
uv run streamlit run app.py
```

Always use `uv run` prefix — it ensures the correct virtual environment and dependencies.

## Key quirks

- **Prompts are separate files** — `prompts/*.md` are loaded at runtime via `Path(__file__).parent.parent / 'prompts' / '...'`. Do not inline prompt text; edit the `.md` files.
- **QA review is inside question generator** — `run_qa_reviewer` is called inside `run_question_generator` (not by the orchestrator). Up to 3 retries happen automatically before returning a fallback question.
- **SRS review woven in every 5th question** — The mastery scorer sets `mastery.next_is_review = True` when `total_questions % 5 == 0` and due cards exist. The orchestrator picks this up in `handle_generate_question`.
- **Integration test has a `time.sleep(3)`** — In `test_pipeline.py` line 138, this is intentional: it lets the background thread for LLM error classification complete. Do not remove or reduce it.
- **Rate-limit backoff** — `config.py` implements exponential backoff (4s → 8s → 16s → 32s → 64s) for 429 errors. Free-tier OpenRouter hits these frequently; the retry loop is deliberate.
- **ThreadPoolExecutor max_workers=2** — In `orchestrator.py:55`, this allows parallel execution (grade + generate next question) while preventing too many concurrent API calls on free tiers.

## Architecture

- Entry point: `app.py` (Streamlit) → `Orchestrator` (event-driven, parallel exec)
- Five agents: `agents/syllabus_mapper`, `agents/question_generator`, `agents/qa_reviewer`, `agents/grader`, `agents/mastery_scorer`, `agents/study_strategy`
- Pydantic schemas in `schemas.py` define all inter-agent contracts
- `database.py` is stdlib sqlite3 — no external DB dependencies
- `srs.py` is pure SM-2 algorithm, stdlib only

## Env config

```bash
cp .env.example .env
# Required: OPENROUTER_API_KEY, OPENROUTER_MODEL (default: meta-llama/llama-3.3-70b-instruct)
# Optional: PROVIDER=nvidia (switches to NVIDIA NIM)
```

## Testing notes

- Unit tests mock nothing — they test real SQLite, real SM-2, real orchestrator routing
- `test_pipeline.py` is an 8-stage end-to-end integration test that hits real LLMs
- Syllabus cache keys are normalised via `cert_name.strip().lower().replace(' ', '_').replace('-', '_')` — two cert names that differ only by spacing/hyphens will share a cache entry