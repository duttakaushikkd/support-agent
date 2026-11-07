# Governance and incident response

## Operating policy

The service may automatically answer only when the ticket is within policy, intent and
urgency confidence meet `AUTO_RESPONSE_THRESHOLD`, retrieval finds documentation above
`RETRIEVAL_THRESHOLD`, and response validation passes. Security incidents, compliance
requests, feature requests, unclear requests, billing queries, and data-residency
requests always go to a human. A blocked response is not sent; the ticket is escalated
with its summary and retrieved sources.

## Risk register

| Risk | Likelihood | Impact | Design mitigation | Accountable owner |
|---|---|---|---|---|
| Confident but incorrect answer | Medium | High | Conservative intent and urgency thresholds, retrieval floor, claim/citation checks, human escalation | Kaushik Dutta |
| Private data in an outbound answer | Medium | Critical | Every draft is scanned for identifiers, secrets, payment data, and sensitive values repeated from the ticket; block and escalate | Kaushik Dutta |
| Prompt injection in ticket text | Medium | High | Separate system and ticket messages; injection signal check blocks and records the decision | Kaushik Dutta |
| Unequal answer quality across customer groups | Medium | High | Segment routing and historical outcomes; human-review answer samples by tier, language fluency, and channel before launch | Kaushik Dutta |
| Stale knowledge base | Medium | High | Identify each passage by source document; assign article owner and review date before production; remove stale passages from retrieval | Kaushik Dutta |
| Provider outage or throttling | High | Medium | One bounded retry, deterministic documentation fallback, then escalation if safe generation/validation cannot proceed | Kaushik Dutta |
| Latency under load | Medium | Medium | Measure end-to-end p95, cap provider timeout/retries, monitor queue and latency, and escalate on timeout | Kaushik Dutta |
| Cost or free-tier limits | Medium | Medium | Free-tier configuration, bounded calls, no provider call for escalated tickets, local fallback | Kaushik Dutta |

The owner assignments are proposed for this individual capstone and must be confirmed
by the student before final submission.

## Decision logging

SQLite records normalized input, prediction and alternatives, calibrated intent and
urgency scores, retrieved passage IDs and relevance scores, threshold, action and reason,
validation results, model/provider identifier, prompt version, requirement identifiers,
latency, and processing errors. For a batch run, reconcile the per-run output with the
persisted decision IDs. Do not expose the database or API keys publicly; the log contains
customer-provided text.

## Fairness review

The 500-ticket development sample contains 380 fluent-English and 120 non-fluent-English
tickets. Historical first-contact resolution is 43.2% vs. 45.8%; historical mean CSAT is
2.95 vs. 3.04. These sample results do not support the interview claim that non-fluent
tickets had worse satisfaction, but they do not rule out differences in response quality.
The automated harness reports subgroup coverage and historical outcomes. Before
deployment, two reviewers must score a stratified response sample and investigate any
quality gap above five percentage points. This review has not been completed for live
responses.

## Incident procedure

1. **Detect:** agent or monitor reports a suspected private-data leak, unsupported answer,
   injection bypass, repeated provider failure, or sudden latency/route change.
2. **Contain:** create `runtime/auto_response.disabled`. The service checks this file on
   every ticket and routes would-be automatic answers to agents. The on-call support lead
   is authorized to create or remove it; no deployment is needed. Confirm by submitting a
   known routine ticket and seeing an escalation.
3. **Assess:** preserve the decision ID, timestamp, input, prediction, sources, response,
   and guardrail results. Identify affected tickets since the last known-good check.
4. **Notify:** tell the support lead and security/privacy contact for any personal-data or
   security incident. The customer communication owner decides what customers need to be
   told under policy.
5. **Remediate:** correct the prompt, policy, corpus, or validator; add a regression case;
   review the affected responses with a human.
6. **Review:** document cause, scope, customer impact, corrective action, owner, and
   restart decision. Re-enable only after the support lead approves a routine-ticket,
   escalation, and guardrail-block rehearsal.

## Non-deployment conditions

Do not enable automatic replies for a production integration until the hidden evaluation
run passes, the human hallucination/citation review and fairness audit are completed, the
quality targets are met or explicitly accepted, the risk owners approve mitigations, and
the incident kill switch has been rehearsed.
