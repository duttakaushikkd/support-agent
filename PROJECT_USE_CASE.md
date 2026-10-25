# CloudServe Support Automation Use Case

## The use case

CloudServe Solutions is a B2B cloud infrastructure and developer-tools company whose support team receives more than 500 tickets a week through email, live chat, API-documentation comments, and a community forum. Customers wait 8–12 hours for a first response despite a two-hour service-level promise. Only 42% of tickets are resolved on first contact, and customer satisfaction is 3.2/5.

Many tickets are routine questions that are already answered in CloudServe's support documentation. The problem is therefore not simply a lack of knowledge: it is getting the right, trustworthy answer to the customer quickly, while ensuring complex or unsafe cases reach a human with the context they need.

**Primary users:** customers seeking support and CloudServe support agents handling escalated cases.

**Desired outcome:** reduce customer waiting time and repetitive agent work without allowing an AI system to send unsupported, unsafe, or privacy-leaking answers.

## What you are supposed to build

Build an intelligent customer-support pipeline/API, not just a conversational UI. It should accept a support ticket and reliably decide whether it can safely answer from CloudServe's documentation or must escalate to a human.

The suggested flow is:

```text
Ticket from any channel
        ↓
Normalise into one ticket format
        ↓
Classify intent and urgency, with confidence
        ↓
Retrieve relevant passages from the supplied knowledge base
        ↓
Route: auto-answer or escalate
        ↓
Generate a grounded answer with verifiable citations
        ↓
Validate for privacy, unsupported claims, and unsafe output
        ↓
Send answer or log an escalation with summary and sources
```

## Required capabilities

Your software must:

- Ingest and normalise tickets from all four channels: email, live chat, documentation comments, and forum posts.
- Classify every ticket by intent and urgency, including a numeric confidence score and a safe fallback for uncertain cases.
- Search the supplied `documentation.json` corpus and return ranked, identifiable source passages.
- Use a deterministic, measured routing threshold to choose auto-response or human escalation.
- Produce answers grounded in retrieved passages, with citations that point to those actual passages.
- Escalate when the question cannot be safely answered, confidence/retrieval quality is insufficient, or the intent is prohibited from auto-response. An escalation should include a useful summary and retrieved sources.
- Run guardrails on every generated response. At minimum, they must detect private data and unsupported claims, and they must be able to block a response.
- Persist a decision log for every ticket: input, predictions, confidence, retrieved sources, route/action, reason, and validation outcome.
- Handle malformed tickets, empty retrieval results, model-provider timeout/outage, and rate limiting without crashing or silently dropping tickets.
- Include an unattended evaluation harness that accepts `--input` and `--output` paths, processes every supplied ticket, creates a metrics report, and requires no manual intervention.
- Include automated tests runnable with one documented command.

## Data you will use

- `development_tickets.json` — 500 labelled tickets for discovery and development.
- `documentation.json` — 29 knowledge-base articles forming the retrieval corpus.
- `ground_truth_responses.json` — 200 senior-agent reference answers to help assess response quality.
- `validation_tickets.json` — 80 tickets for evaluation.

Your evaluator must work with any file that follows the ticket schema, because marking uses an unseen set of 120 tickets. Do not hard-code the provided validation filename or tune implementation specifically to a hidden test set.

## How success is judged

The intended product outcomes are:

- First-contact resolution: at least 60% (baseline: 42%).
- First response: under 5 minutes (baseline: 8–12 hours).
- Customer satisfaction: at least 4.0/5 (baseline: 3.2/5).
- Escalation rate: 30% or lower (baseline: 58%).

Key quality constraints are intent precision of at least 85%, hallucination rate at most 5%, citation accuracy at least 95%, and p95 response latency under 3 seconds. Governance is non-negotiable: no private data in outbound responses, every automated decision logged, calibrated confidence, and response-quality gaps below five percentage points across customer groups.

## Technical direction and boundaries

The pack recommends Python 3.10+, FastAPI, LangChain/LangGraph, Chroma, `all-MiniLM-L6-v2` embeddings, SQLite or PostgreSQL for logs, and a free-tier model provider such as OpenRouter or Groq. You can adapt the architecture if you can justify it.

The most important deliverable is a clean-checkout, end-to-end system—not a notebook or a demo on selected tickets. Someone should be able to follow your README, start the system, run one command against an input ticket file, and receive complete outputs, a decision log, and a metrics report.

## What is deliberately out of scope

- Replacing support agents entirely.
- Answering when the system lacks reliable documentation support.
- Treating escalation as failure; safe escalation is a core feature.
- A polished chat interface without the underlying ingestion, retrieval, routing, validation, logging, and evaluation workflow.

## One-sentence project statement

Build a reliable support-automation service that uses CloudServe's documentation to answer routine tickets quickly with verifiable citations, while safely escalating uncertain, complex, or risky cases to human agents with actionable context.
