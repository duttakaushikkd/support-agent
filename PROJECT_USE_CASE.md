# CloudServe Support Automation Capstone

## Project purpose

CloudServe Solutions is a software company of about 150 people serving just over 200 corporate customers. Its support team receives more than 500 tickets each week across email, live chat, documentation comments, and a community forum. First replies take 8–12 hours against a two-hour service commitment; fewer than half of tickets are resolved without escalation, and customer satisfaction is 3.2/5.

The client initially asks for a chatbot. The project is to investigate the support problem and build the system the evidence justifies: a reliable support automation service that quickly resolves routine, documented questions and safely hands uncertain, complex, or risky cases to human agents. A chatbot interface alone does not meet the use case.

**Primary users:** customers requesting support and CloudServe agents receiving escalations.

**Intended outcomes:** improve first-contact resolution from 42% to at least 60%, reduce first response to under five minutes, improve satisfaction from 3.2/5 to at least 4.0/5, and keep escalation at or below 30%, while meeting the safety and quality controls below. These are project targets; report measured results and limitations honestly rather than presenting targets as achieved outcomes.

## System to build

Build a working, end-to-end support pipeline and API that accepts an individual ticket or a file of tickets. It must run from a clean checkout by following the repository README and process the complete supplied evaluation input unattended in one run. The evaluator must accept explicit input and output paths so it can process unseen files that follow the ticket schema.

```text
Email / chat / documentation comment / forum ticket
                         ↓
            Normalize and preserve original
                         ↓
             Classify intent and urgency
             with confidence and alternatives
                         ↓
       Retrieve ranked passages from documentation
                         ↓
      Deterministic policy and threshold routing
              ↙                         ↘
    Grounded cited response         Human escalation
              ↓                         ↓
       Privacy and grounding validation; block if unsafe
                         ↓
          Deliver response or escalation context
                         ↓
       Persistent decision log and evaluation metrics
```

### Required behavior

- Ingest tickets from all four channels and normalize them into one internal representation. Preserve source channel and original text; tolerate missing fields, unusual characters, and empty bodies.
- Classify every ticket by intent and urgency, attach a numeric confidence from 0 to 1, preserve plausible alternatives, and use a defined fallback for uncertain or malformed cases.
- Retrieve ranked, scored, identifiable passages from the supplied `documentation.json` corpus. Apply a relevance threshold and return no sources when none are relevant. Source identifiers and citations must resolve to actual passages.
- Apply a deterministic, measured routing threshold. The same ticket and configuration must yield the same route. Escalate when confidence or retrieval quality is insufficient, the request is unsupported or unsafe, or policy prohibits automated response. Include a useful draft summary and retrieved sources in escalations.
- Generate structured answers grounded in retrieved documentation, with citations attached to supported claims. Say when the system does not know. Keep ticket text separate from system instructions so customer content cannot redirect the system.
- Validate every generated response before release. At minimum, detect private data and unsupported claims; checks must be able to block and escalate. Also enforce instruction integrity, support scope/tone, and confidence-floor controls. Record check results whether the answer passes or is blocked.
- Persist a reconstructable decision log for every ticket, including input or summary, predictions and confidence, alternatives, sources and scores, threshold, route/action and reason, model/prompt version where applicable, guardrail results, and validation outcome. Logged decisions must reconcile exactly with processed tickets.
- Continue safely through malformed input, empty retrieval, model-provider timeout/outage, and rate limiting; do not crash or silently drop tickets.
- Provide an unattended evaluation harness with `--input` and `--output` arguments. It must process every ticket and automatically produce complete outputs, a persistent decision log, and a metrics report.
- Include automated tests runnable with one documented command.

### Evaluation report produced by the harness

The report must calculate, rather than require manual post-processing of:

- Volume: tickets processed, automatically answered, escalated, and blocked.
- Business outcomes: first-contact resolution, mean and median time to first reply, and escalation rate.
- Technical performance: intent precision and recall per class, retrieval hit rate, and median and p95 latency.
- Governance: tickets and decisions logged, guardrail activations by type, and private-data detections.

Evaluation targets and quality constraints include intent precision ≥85%, hallucination rate ≤5%, citation accuracy ≥95%, p95 response latency <3 seconds, zero private data in outbound text, complete decision logging, confidence calibration within five percentage points, and response-quality variation below five percentage points across customer groups. Measure satisfaction with a clearly described human-review proxy because no live customer satisfaction data is supplied. Report escalation with first-contact resolution, and state the method, sample, and uncertainty behind human-scored measures.

## Supplied data and evaluation boundary

The pack provides 500 labelled `development_tickets.json` tickets, 29 knowledge-base articles in `documentation.json`, 200 senior-agent references in `ground_truth_responses.json`, 80 `validation_tickets.json` tickets, and five stakeholder interview transcripts. Use the interviews and ticket evidence to discover and justify the problem and requirements; do not invent discovery findings.

The final assessment uses an unseen set of 120 tickets drawn from the same population and schema. The harness must accept any conforming input file, not hard-code a provided validation filename or tune specifically to a hidden set. The project instructions call for one hidden-set evaluation run; record its date, ticket count, system version, and run count in the report. Develop and tune using development data and appropriate local validation instead.

## Technical direction and boundaries

Python 3.10+, FastAPI, LangChain or LangGraph, Chroma, `all-MiniLM-L6-v2`, SQLite or PostgreSQL, and a free-tier provider such as OpenRouter or Groq are suggested, not mandatory. Alternative architectures are acceptable when justified. Free/open-source tools and provider free tiers are sufficient; paid capacity is not expected.

The system should support human agents, not replace them. It must not answer when reliable documentation support is absent. Escalation is a valid safety outcome. A polished interface without ingestion, retrieval, routing, validation, logging, and evaluation does not satisfy the use case.

## Project stages and required artefacts

Work individually through the six stages, in order:

1. **Discovery:** complete the discovery workbook using stakeholder interviews and ticket evidence; document an evidence-backed problem statement.
2. **Requirements:** produce requirements version one and trace each requirement to discovery evidence.
3. **Prompt library:** translate requirements into specifications and versioned prompts.
4. **Sprint plan:** plan the backlog, estimates, ownership, and definitions of done.
5. **Build, evaluate, and revise:** implement the system, run evaluation, and make at least one substantive requirements revision with its trigger recorded in the revision log.
6. **Governance and submission:** complete risk, fairness, logging, and incident-response work; produce the report, video, effort log, and packaged repository.

The repository must include a working README, pinned `requirements.txt`, placeholder-only `.env.example`, organized `src/`, versioned `prompts/`, `tests/`, `evaluation/`, `docs/`, small sample data or data guidance, and `.github/workflows/` CI configuration. Include the complete repository and its history; do not include credentials. Attribute substantial work not written by the student, including AI-generated code. AI tools are permitted and expected, and their use must be declared in the report along with where outputs were corrected or overridden.

## Submission requirements

Submit one ZIP archive named exactly `FirstnameLastname_Capstone_Submission.zip` (use the student's enrolled first and last name; no spaces, dates, or version suffixes). It must contain exactly these four top-level folders, in this order:

```text
01_Video/
02_Report/
03_Workbooks/
04_Source_Code/
```

- **`01_Video/`** — one 18–22 minute presentation, MP4 at 1080p or better, named `FirstnameLastname_Capstone_Video.mp4`; if too large, provide a text file containing a shareable link. The student must appear on camera for the introduction and close, and the video must include at least seven minutes of live system demonstration: a successful answer, an escalation, a guardrail block, and evidence of the unattended full evaluation run. Follow the prescribed presentation flow: problem, discovery, system, demonstration, results, governance/risk, and next steps. Audio must be clear and screen content legible.
- **`02_Report/`** — one 20–30 page PDF excluding appendices, named `FirstnameLastname_Capstone_Report.pdf`. Use the submission guide's section order: executive summary; problem; discovery findings; requirements; architecture and design; implementation; evaluation; governance and risk; requirements revision; conclusions; appendices. Number, caption, and reference every figure and table. Support performance claims with their measurement method and data. Include the evaluation date and run count, uncertainty and limitations, and an AI-use declaration.
- **`03_Workbooks/`** — all five genuinely completed stage workbooks (discovery, requirements, prompt library, sprint plan, and requirements revision log), in PDF or DOCX, plus the effort log named `FirstnameLastname_Effort_Log.pdf`. The effort log records actual task-level hours by day and stage throughout the project, at least every second day.
- **`04_Source_Code/`** — the complete repository as a folder or nested archive, including history, tests, and working README. It must run from a clean checkout on another machine. Include no API keys, tokens, or passwords in files or history.

The student-confirmed submission deadline is **13 November 2026**. Submission within 48 hours after the deadline receives a deduction; later work is not marked without an extension agreed in advance. Before packaging, follow the README from a fresh checkout, run the full evaluation unattended in one run, reconcile its report and decision log, run the documented test command, check credentials and attribution, and confirm all four archive folders and required artefacts are present.

## One-sentence project statement

Build and evaluate a clean-checkout support automation service for CloudServe that resolves routine tickets from its documentation with verifiable citations, while consistently escalating uncertain, unsupported, complex, or risky cases to human agents with useful context and a complete audit trail.
