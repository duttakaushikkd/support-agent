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

For a full run, make sure the capstone data pack is available under
`FDE_Capstone_Complete/Capstone_Pack/05_Datasets` or set `DATA_DIR` in `.env` to
the directory containing `development_tickets.json` and `documentation.json`. A
small synthetic fixture is selected only when the real pack is absent so the API
and tests can start from a clean checkout; it is not suitable for evaluation.

An API key is optional. Without one, the system uses a deterministic local grounded
response so that tests and unattended evaluation can still run. To use Groq, set
`GROQ_API_KEY` in `.env`; the default model is `llama-3.3-70b-versatile`. To use
OpenRouter instead, set `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY`; the
default model is `openrouter/free`. You can override `LLM_MODEL` or the full chat
completion endpoint with `LLM_BASE_URL`. The application calls the provider over
HTTP directly and does not require a provider SDK. See the [Groq API reference](https://console.groq.com/docs/api-reference)
and [OpenRouter chat completion documentation](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).

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
  --input FDE_Capstone_Complete/Capstone_Pack/05_Datasets/validation_tickets.json \
  --output evaluation/results
```

This creates `decisions.json` and `metrics.json`. The input path is always explicit,
so the same command works with an unseen evaluation file using the documented schema.
The input path is independent of the training and documentation directory. Set
`DATA_DIR` in `.env` when those files live somewhere else.

## Run tests

```bash
python -m pytest tests/ -v
```

## Safety policy

Security, compliance, feature-request, unclear-request, billing, and data-residency
tickets always escalate. Automated answers require the conservative default confidence
threshold of 0.55 (configure it with `AUTO_RESPONSE_THRESHOLD`) and relevant documentation.
The classifier uses cross-validated sigmoid calibration; validate the routing threshold
on a local holdout before reporting its operating point. Guardrails block private data,
unsupported claims or invalid citations, prompt-injection signals, and out-of-scope
commitments. Every outcome is persisted in
SQLite (default: `runtime/support_agent.db`).

## Repository structure

The repository follows the submission guide: application code in `src/`, versioned
prompts in `prompts/`, automated tests in `tests/`, the batch evaluator in
`evaluation/`, architecture notes in `docs/`, sample-data guidance in `data/`, and
the GitHub Actions test workflow in `.github/workflows/`. Capstone-provided datasets
remain under `FDE_Capstone_Complete/Capstone_Pack/05_Datasets` in this workspace and
are not duplicated into the application package.
