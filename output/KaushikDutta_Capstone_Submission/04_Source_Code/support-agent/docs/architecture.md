# Architecture and design decisions

## Request flow

`POST /ticket` and the browser chat use the same `SupportService` as the evaluator.
The API accepts one ticket. The evaluator calls the service for each input list item.
The pipeline normalizes the channel and preserves the ticket text, predicts intent
and urgency, retrieves documentation passages, applies deterministic routing, drafts
only if policy permits, validates each draft, and writes one SQLite decision record.
The UI displays only the drafted answer or a human-review notice. The API and SQLite
decision log retain routing reasons, sources, citations and diagnostics. The
compatibility route `/tickets` reaches the same handler.

## Classification and confidence

Intent and urgency use separate scikit-learn `TfidfVectorizer` plus calibrated
`LogisticRegression` classifiers trained on `development_tickets.json`. A prediction
includes the top intent alternatives, urgency alternatives and separate confidence
scores. Intent and urgency use separate provisional policy floors (0.60 and 0.45). A
stratified 20% development holdout found the shared 0.55 floor routed only 18% of
tickets to auto-response; the separate floors yielded 52% coverage and 82.7% precision
against expected-route labels. Urgency accuracy on that holdout was only 41%, so the
score is a weak signal and both floors require further validation. Security,
compliance, feature requests, unclear requests, billing and data residency always
route to an agent.

## Retrieval and chunking choice

The 29 supplied articles are split into 800-character windows with 120-character
overlap. TF-IDF unigram/bigram vectors are explicitly stored in a persistent Chroma
collection. Search computes local cosine-equivalent scores from the same normalized
TF-IDF vectors, applies `RETRIEVAL_THRESHOLD`, and returns stable document/chunk IDs.
When Chroma is unavailable, the same local vector ranking keeps the service usable.

The setup guide calls for comparing at least two chunking choices. The checked-in
`evaluation/retrieval_ablation.py` compares heading-delimited Markdown sections with
800/120 character windows on 357 answerable development tickets, top three documents,
and a 0.08 relevance threshold. Results:

| Strategy | Chunks | Top 1 expected document hit | Top 3 expected document hit | MRR@3 |
|---|---:|---:|---:|---:|
| Markdown sections | 261 | 81.5% | 92.7% | 0.868 |
| 800 chars / 120 overlap | 58 | 86.8% | 93.3% | 0.898 |

Fixed windows are selected because they performed at least as well on expected
document hits, improve the top-ranked hit, and create fewer, larger indexed passages.
This development-label comparison is a retrieval proxy, not answer-quality evidence.
Do not tune chunking on the hidden assessment set.

## Generation and reference responses

Groq/OpenRouter is optional. The provider call receives separate system instructions
and untrusted ticket text, along with only retrieved passages and their allowed IDs.
The output contract is JSON with an answer and citation IDs. The local fallback quotes
retrieved source text and attaches its actual chunk ID. Provider timeout, rate limit,
or invalid output falls back locally; all drafts still pass the validator.

`ground_truth_responses.json` contains 200 senior-agent examples tied to development
ticket IDs. The runtime never fetches a reference response to answer a customer. The
evaluator optionally joins those records by ticket ID and checks expected source IDs,
`must_mention`, and `must_not_claim` phrases. Exact phrase matching is only a
screening proxy; it cannot judge semantic equivalence, completeness, or tone. The
80-ticket validation set has no IDs matching the ground-truth examples.

## Validation and routing

The router is deterministic for the same ticket, fitted data and settings. Empty or
low-score retrieval, low confidence, restricted intent, injection signals, kill
switch state or failed validation prevent an automatic reply. Injection signals are
checked before generator invocation. The response validator checks PII, whether each
factual sentence is cited, citation/source resolution, lexical claim support, and
scope/commitment language. Its lexical support check can miss paraphrased unsupported
claims and block safe paraphrases; human assessment remains necessary.

## Decision record

SQLite has one durable row for each processed ticket. The row includes UTC timestamp,
ticket ID/channel, decision stage, normalized input, classifier predictions and
alternatives, model identity/version, retrieved source IDs and scores, threshold,
action, reason and escalation summary, prompt version, requirement IDs, guardrail
results, latency and error type. Both intent and urgency thresholds are persisted
independently. Existing SQLite databases are upgraded additively for the audit
columns. The output `decisions.json` contains the matching persistent decision ID so
run records can be reconciled.

## Observability and deployment boundary

FastAPI exposes Prometheus metrics at `/metrics`: processed tickets by channel/action,
latency histogram, guardrail activations and classifier-confidence histograms. The
starter scrape configuration and Grafana dashboard are in `monitoring/`. Availability
requires a defined monitored time window and cannot be inferred from an offline run.
SQLite and Chroma files are runtime state and are ignored by Git. Protect their access
and define retention before using real customer content.
