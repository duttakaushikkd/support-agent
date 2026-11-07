# Prompt register

| Prompt | Version | Purpose | Called at |
|---|---|---|---|
| `generation_v1.md` | v1 | Draft a concise, courteous, source-grounded support answer in JSON. Ticket text is untrusted; each factual sentence needs a resolvable citation. | Only after routing permits an automatic response. |
| `review_v1.md` | v1 | Structured rubric for checking claim support, citation resolution, completeness, privacy and scope. | Human/review tooling; not a model call in the current service. |
| `evaluation_v1.md` | v1 | Human evaluation rubric for answer quality and policy adherence. | Evaluation design; not a runtime model call. |

The prompt is paired with deterministic Python guardrails in `src/validator.py`.
`ground_truth_responses.json` supplies expected documents and must-mention/must-not-
claim criteria to the evaluation harness when ticket IDs match. Reference answers are
not inserted into the runtime prompt and are not returned to customers.

Provider output must be a JSON object with `answer` and `citations`. Citations must
be chunk IDs returned by the current retrieval call; a malformed provider response,
provider timeout or rate limit falls back to a local source-based answer, which still
passes through the same validator.
