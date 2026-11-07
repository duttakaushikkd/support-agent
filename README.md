# CloudServe Support Automation

A human-supervised support ticket service for the FDE capstone. It accepts one
ticket through FastAPI or the browser chat, normalizes its channel, predicts intent
and urgency, retrieves cited passages from the supplied documentation, and either
returns a validated draft or prepares an escalation. Every processed ticket is
written to SQLite. A separate harness processes ticket files unattended and writes
per-ticket decisions and a metrics report.

## Requirements and data

- Python 3.11 or later (CI uses Python 3.11).
- Git.
- The capstone pack at `FDE_Capstone_Complete/Capstone_Pack/05_Datasets`, or a
  `DATA_DIR` pointing to a folder containing `development_tickets.json` and
  `documentation.json`.
- A Groq or OpenRouter API key is optional. Without one, the service uses a
  deterministic answer built from retrieved documentation; it never needs a paid
  provider to start or evaluate.

The setup guide proposes Chroma with `all-MiniLM-L6-v2`. This implementation uses
TF-IDF vectors persisted in Chroma instead. This keeps setup local, avoids model
downloads, and gives reproducible retrieval without a network call. The index is
rebuilt/upserted from the configured corpus at startup. A development-only comparison
of Markdown sections and 800-character windows with 120-character overlap found a
slightly higher expected-document hit@3 for fixed windows (93.3% vs. 92.7%; top-1
86.8% vs. 81.5%) on 357 answerable development tickets. Fixed windows are therefore
the current choice; this label-based retrieval proxy is not proof of answer quality.
See `docs/architecture.md` and `evaluation/retrieval_ablation.py`.

## Install

Run these commands from the repository root:

```bash
python3 --version
git --version
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Edit `.env` only if you need to select a different data directory, storage path, or
model provider. Put the provider key in `.env`; never paste it into source code,
GitHub Actions, or a report. `.env` and runtime storage are ignored by Git.

If you configured a provider key, verify it without starting the service:

```bash
python scripts/check_provider.py
```

This makes one small chat-completions request and prints the short provider reply.
Skip this check when using the credential-free local fallback.

Important settings:

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | Found capstone pack, then test fixtures | Dataset directory. Set this explicitly when the pack is elsewhere. |
| `LLM_PROVIDER` | `groq` | `groq` or `openrouter`. |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` | empty | Optional provider key. |
| `LLM_MODEL` | provider default | Model name sent to the provider. |
| `LLM_BASE_URL` | provider default | Optional chat-completions endpoint override. |
| `DATABASE_URL` | `sqlite:///runtime/support_agent.db` | Persistent decision log. |
| `CHROMA_PATH` | `runtime/chroma` | Persistent local Chroma index. |
| `AUTO_RESPONSE_THRESHOLD` | `0.55` | Provisional fixed routing floor applied to both intent and urgency confidence. |
| `RETRIEVAL_THRESHOLD` | `0.08` | Minimum TF-IDF relevance score for returned passages. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Character window and overlap selected from the documented development-only ablation. |
| `AUTO_RESPONSE_KILL_SWITCH_FILE` | `runtime/auto_response.disabled` | If this file exists, would-be automatic replies route to a human. |
| `GROUND_TRUTH_PATH` | `DATA_DIR/ground_truth_responses.json` if present | Optional evaluation rubric; accepts the singular legacy filename too. |

The 0.55 score floor is a conservative project policy value, not a guarantee that
scores are calibrated. The harness reports calibration error so it can be assessed
against the five percentage point target. Do not describe a confidence score as an
actual probability without calibration evidence.

## Start the API and chat interface

Start the service using either command:

```bash
python -m src.api
# or
uvicorn src.api:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) for the chat interface. Choose a
channel and customer metadata, enter the subject and message, and send the ticket.
The browser submits one ticket at a time to `POST /ticket`. The interface shows the
assistant draft or escalation/block decision, the sources considered, confidence,
citations, guardrail results, and the SQLite decision ID. User-entered text is
rendered as text, not HTML.

Other endpoints:

- `POST /ticket`: process one JSON ticket and return a structured decision.
- `POST /tickets`: compatibility alias for `POST /ticket`.
- `GET /health`: check that the classifier, retrieval corpus, database and provider
  mode initialize.
- `GET /metrics`: Prometheus text metrics.
- `GET /docs`: interactive OpenAPI documentation.

Example API request:

```bash
curl -sS http://127.0.0.1:8000/ticket \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id":"LOCAL-001","channel":"chat","subject":"Login fails","body":"The console says invalid credentials. What should I check?","customer_tier":"standard","customer_region":"APAC","language_fluency":"fluent"}'
```

Allowed channels are `email`, `chat`, `docs_comment`, and `forum`. Missing subject or
body fields are normalized; unsupported channels and malformed JSON values are
logged as safe escalations where the request reaches the application. A routine
ticket can still be escalated because of confidence, policy, retrieval quality, a
guardrail, or the kill switch. Escalation is an expected safe outcome.

To stop automatic replies immediately, create
`runtime/auto_response.disabled`. Remove it to re-enable the configured policy.
Restrict access to that file in a deployed environment.

## Run the unattended evaluation

The command accepts any schema-compatible input path and output directory. It
processes every list item, writes `decisions.json` and `metrics.json`, and persists
each decision to the configured SQLite database:

```bash
python -m evaluation.harness \
  --input FDE_Capstone_Complete/Capstone_Pack/05_Datasets/validation_tickets.json \
  --output evaluation/results/visible-run
```

To enable matched reference checks when using development tickets, pass the supplied
senior-agent rubric explicitly:

```bash
python -m evaluation.harness \
  --input FDE_Capstone_Complete/Capstone_Pack/05_Datasets/development_tickets.json \
  --output evaluation/results/development-reference-check \
  --ground-truth FDE_Capstone_Complete/Capstone_Pack/05_Datasets/ground_truth_responses.json
```

`ground_truth_responses.json` has 200 reference responses joined to development
tickets by `ticket_id`. Its `expected_doc_ids`, `must_mention`, and `must_not_claim`
fields provide evaluation criteria. The reference answer is an example of the desired
support style, not a runtime answer template. The evaluator reports retrieval hits and
exact phrase checks for the matched answers; these automated checks do not replace
semantic human assessment. The visible 80-ticket validation set has no ticket IDs in
common with the 200 references, so its reference-response coverage is zero.

The metrics report includes volume by action, historical outcome fields, automatic
response coverage (separate from actual FCR), first-reply time when input timestamps
exist, per-class intent and urgency precision/recall, confusion matrices, retrieval
hit rate, routing accuracy, median/p95 local processing latency, confidence
calibration, group coverage/outcome summaries, guardrail events, citation/grounding
proxies, log reconciliation, reference checks, dataset hash, run timestamps, and
system revision. Where inputs cannot establish a measure—such as system FCR,
customer-visible reply time, availability, semantic hallucination, or answer quality
by group—the report records `null` and explains why rather than guessing.

Do not use the hidden 120-ticket set for development or threshold tuning. The
assessment run is performed once by the evaluator; report its date, ticket count,
system version and run count when those results are available.

## Retrieval chunking comparison

The setup guide asks for at least two chunking configurations to be compared. Run the
development-only ablation before selecting/changing a chunking strategy:

```bash
python -m evaluation.retrieval_ablation \
  --data-dir FDE_Capstone_Complete/Capstone_Pack/05_Datasets \
  --output evaluation/results/retrieval-chunking.json
```

It compares Markdown sections against 800-character windows with 120-character
overlap using expected document hit at 1 and 3. These are retrieval proxies on
development labels, not final assessment results.

## Decision log and monitoring

SQLite stores one record per processed ticket, including timestamp, channel, stage,
normalized input, classifier values and alternatives, retrieved passages and scores,
threshold, model and version, action, reason, prompt version, requirement IDs,
guardrail results, latency, and any processing error. Existing SQLite files are
upgraded additively when the service starts. The evaluator reconciles its output
decisions with non-null persistent decision IDs.

Prometheus counters and histograms are exposed at `/metrics`: tickets by channel and
action, end-to-end service latency, guardrail blocks by type, and intent/urgency
confidence distributions. `monitoring/prometheus.yml` and
`monitoring/grafana_dashboard.json` are provided as starter configuration. For a
native Prometheus install, scrape `localhost:8000`; when Prometheus runs in Docker on
macOS/Windows, use `host.docker.internal:8000`. Import the dashboard JSON into
Grafana and select the Prometheus data source. A single offline evaluation does not
establish the 99.5% availability target; monitor over a defined service window.

## Tests and CI

Run the complete local suite with one command:

```bash
python -m pytest tests/ -v
```

GitHub Actions runs the same command on pushes and pull requests using Python 3.11.
Tests use local fixtures and do not require provider credentials.

## Safety and operational limits

Security, compliance, feature-request, unclear-request, billing, and data-residency
tickets always escalate. Intent and urgency are independent scikit-learn classifiers;
retrieval is TF-IDF over supplied article sections persisted in Chroma. Groq or
OpenRouter is optional and only drafts answers after policy routing. Provider timeout
or rate limit falls back to a local source-based response; that response still passes
the same validator. Instruction-integrity checks run before sending ticket text to
the generator, and PII, grounding, citation, and scope/tone checks can block a draft.

Automated lexical checks are safety filters, not proof of semantic correctness. Before
any real customer pilot, perform the evaluation framework's two-assessor review of at
least 50 responses, measure subgroup response quality, verify provider outage behavior,
define log privacy/retention controls, and run the clean-checkout and hidden-set gates.

## Repository structure

```text
src/                 FastAPI, chat UI, classifiers, retrieval, generation, validators, persistence
prompts/             Versioned generation and evaluation prompts
evaluation/          Batch metrics and retrieval chunking comparison
tests/               Credential-free component and API tests
docs/                Architecture and governance notes
monitoring/          Prometheus scrape config and Grafana starter dashboard
FDE_Capstone_Complete/Capstone_Pack/  Supplied instructions, datasets and references
runtime/              Generated SQLite/Chroma state (ignored by Git)
```
