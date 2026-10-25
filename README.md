# CloudServe Support Automation

A safe retrieval-grounded support service for the CloudServe capstone. It accepts
tickets from four channels, classifies and routes them, retrieves evidence from the
provided documentation, validates drafts, logs every decision, and evaluates a whole
ticket file without manual intervention.

## Setup

Requires Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
```

An API key is optional. Without one, the system uses a deterministic local grounded
response so that tests and unattended evaluation can still run. To use an
OpenAI-compatible provider, add `OPENAI_API_KEY`, or `LLM_API_KEY`, `LLM_BASE_URL`,
and `LLM_MODEL`, to `.env`.

## Run the API

```bash
uvicorn src.api:app --reload
```

Open `http://127.0.0.1:8000/docs` to submit `POST /tickets`. `GET /health` checks
the database, retrieval layer, and configured provider mode. Open
`http://127.0.0.1:8000/` for a small browser-based ticket tester.

## Run the unattended evaluator

```bash
python -m evaluation.harness \
  --input Capstone_Pack/05_Datasets/validation_tickets.json \
  --output evaluation/results
```

This creates `decisions.json` and `metrics.json`. The input path is always explicit,
so the same command works with a hidden evaluation file using the documented schema.

## Run tests

```bash
python -m pytest tests/ -v
```

## Safety policy

Security, compliance, feature-request, unclear-request, billing, and data-residency
tickets always escalate. Automated answers require the conservative default confidence
threshold of 0.55 (configure it with `AUTO_RESPONSE_THRESHOLD`) and relevant documentation.
and relevant documentation. Guardrails block private data, unsupported citations,
prompt-injection signals, and out-of-scope commitments. Every outcome is persisted in
SQLite (default: `runtime/support_agent.db`).

## Repository structure

The repository follows the submission guide: application code in `src/`, versioned
prompts in `prompts/`, automated tests in `tests/`, the batch evaluator in
`evaluation/`, architecture notes in `docs/`, sample-data guidance in `data/`, and
the GitHub Actions test workflow in `.github/workflows/`. Capstone-provided datasets
remain in `Capstone_Pack/05_Datasets` and are not duplicated.
