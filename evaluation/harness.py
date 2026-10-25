from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from src.service import SupportService


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    return sorted(values)[min(len(values) - 1, int(len(values) * p))]


def evaluate(input_path: Path, output_dir: Path) -> dict:
    tickets = json.loads(input_path.read_text())
    if not isinstance(tickets, list):
        raise ValueError("Input must be a JSON list of tickets")
    output_dir.mkdir(parents=True, exist_ok=True)
    service = SupportService()
    decisions = [service.process(ticket).to_dict() for ticket in tickets]
    (output_dir / "decisions.json").write_text(json.dumps(decisions, indent=2))
    actions = Counter(d["action"] for d in decisions)
    latencies = [d["latency_ms"] for d in decisions]
    logged = sum(1 for d in decisions if d["decision_id"] is not None)
    correct_intent = [d["prediction"]["intent"] == t.get("labels", {}).get("intent") for d, t in zip(decisions, tickets)]
    expected_docs = [set(t.get("labels", {}).get("expected_doc_ids", [])) for t in tickets]
    retrieval_hits = [bool({s["doc_id"] for s in d["sources"]} & docs) if docs else not d["sources"] for d, docs in zip(decisions, expected_docs)]
    report = {
        "volume": {"processed": len(decisions), "answered": actions["auto_respond"], "escalated": actions["escalate"], "blocked": actions["block"]},
        "business": {"first_contact_resolution_proxy": actions["auto_respond"] / len(decisions) if decisions else 0,
                     "escalation_rate": actions["escalate"] / len(decisions) if decisions else 0},
        "technical": {"intent_accuracy": sum(correct_intent) / len(correct_intent) if correct_intent else 0,
                      "retrieval_hit_rate": sum(retrieval_hits) / len(retrieval_hits) if retrieval_hits else 0,
                      "latency_ms_median": median(latencies) if latencies else 0, "latency_ms_p95": percentile(latencies, .95)},
        "governance": {"decisions_logged": logged, "log_coverage": logged / len(decisions) if decisions else 1,
                       "guardrail_activations": sum(1 for d in decisions if d["action"] == "block")},
    }
    segments: dict[str, dict[str, dict[str, float]]] = {}
    for field in ("customer_tier", "customer_region", "language_fluency"):
        groups: dict[str, list[dict]] = defaultdict(list)
        for ticket, decision in zip(tickets, decisions):
            groups[str(ticket.get(field, "unknown"))].append(decision)
        segments[field] = {name: {"count": len(rows), "auto_response_rate": sum(r["action"] == "auto_respond" for r in rows) / len(rows)} for name, rows in groups.items()}
    report["fairness_segments"] = segments
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CloudServe support evaluation unattended")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
