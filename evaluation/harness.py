from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from src.service import SupportService


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _labels(ticket: Any) -> dict[str, Any]:
    return _mapping(_mapping(ticket).get("labels"))


def _history(ticket: Any) -> dict[str, Any]:
    return _mapping(_mapping(ticket).get("history"))


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p is in the inclusive range 0..1)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))]


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _parse_received_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _classification_metrics(decisions: list[dict], tickets: list[dict]) -> dict[str, Any]:
    labels = sorted({
        label
        for ticket, decision in zip(tickets, decisions)
        for label in (_labels(ticket).get("intent"), decision["prediction"]["intent"])
        if isinstance(label, str)
    })
    confusion = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for ticket, decision in zip(tickets, decisions):
        actual = _labels(ticket).get("intent")
        predicted = decision["prediction"]["intent"]
        if actual in confusion and predicted in confusion[actual]:
            confusion[actual][predicted] += 1
    per_class: dict[str, dict[str, float | int | None]] = {}
    for label in labels:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[actual][label] for actual in labels)
        precision = _ratio(tp, predicted_count)
        recall = _ratio(tp, support)
        f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
    evaluated_classes = [m for m in per_class.values() if m["precision"] is not None and m["recall"] is not None]
    macro = {
        name: mean(float(row[name]) for row in evaluated_classes) if evaluated_classes else None
        for name in ("precision", "recall", "f1")
    }
    total = sum(sum(row.values()) for row in confusion.values())
    correct = sum(confusion[label][label] for label in labels)
    return {
        "evaluated_tickets": total,
        "accuracy": _ratio(correct, total),
        "macro": macro,
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def _confidence_calibration(decisions: list[dict], tickets: list[dict], bands: int = 5) -> dict[str, Any]:
    rows = []
    weighted_error = 0.0
    total = 0
    for band in range(bands):
        low, high = band / bands, (band + 1) / bands
        members = []
        for decision, ticket in zip(decisions, tickets):
            labels = _labels(ticket)
            if not labels.get("intent"):
                continue
            prediction = decision["prediction"]
            confidence = float(prediction.get("confidence", 0.0))
            if low <= confidence < high or (band == bands - 1 and confidence == 1.0):
                members.append((confidence, prediction["intent"] == labels["intent"]))
        if not members:
            continue
        stated = mean(confidence for confidence, _ in members)
        observed = mean(float(correct) for _, correct in members)
        weighted_error += abs(stated - observed) * len(members)
        total += len(members)
        rows.append({"band": f"{low:.1f}-{high:.1f}", "count": len(members),
                     "mean_stated_confidence": stated, "observed_accuracy": observed,
                     "absolute_gap": abs(stated - observed)})
    return {"bands": rows, "expected_calibration_error": _ratio(weighted_error, total),
            "calibration_sample_size": total,
            "target_max_gap": 0.05,
            "note": "Small per-band samples make calibration estimates noisy; interpret alongside sample counts."}


def _retrieval_metrics(decisions: list[dict], tickets: list[dict]) -> dict[str, Any]:
    eligible = 0
    hits = 0
    for decision, ticket in zip(decisions, tickets):
        labels = _labels(ticket)
        raw_expected = labels.get("expected_doc_ids", [])
        expected = set(raw_expected) if isinstance(raw_expected, list) else set()
        if not labels.get("answerable_from_docs", bool(expected)) or not expected:
            continue
        eligible += 1
        found = {source["doc_id"] for source in decision["sources"]}
        hits += bool(expected & found)
    return {"answerable_tickets_with_expected_sources": eligible, "expected_source_hits": hits,
            "hit_rate": _ratio(hits, eligible)}


def _business_metrics(decisions: list[dict], tickets: list[dict]) -> dict[str, Any]:
    histories = [_history(ticket) for ticket in tickets]
    known_fcr = [h["first_contact_resolution"] for h in histories if isinstance(h.get("first_contact_resolution"), bool)]
    csat = [float(h["csat_rating"]) for h in histories if isinstance(h.get("csat_rating"), (int, float))]
    escalations = sum(d["action"] in {"escalate", "block"} for d in decisions)
    auto_answers = sum(d["action"] == "auto_respond" for d in decisions)
    latencies = [float(d["latency_ms"]) for d in decisions]
    received = [_mapping(t).get("received_at") for t in tickets]
    has_received_timestamps = sum(_parse_received_at(value) is not None for value in received)
    return {
        "first_contact_resolution_proxy": {
            "rate": _ratio(auto_answers, len(decisions)),
            "auto_answered_tickets": auto_answers,
            "method": "Auto-response coverage proxy; an automated answer is not proof the issue was resolved.",
        },
        "historical_ticket_outcomes": {
            "first_contact_resolution_rate": _ratio(sum(known_fcr), len(known_fcr)) if known_fcr else None,
            "observed_tickets": len(known_fcr),
        },
        "escalation_rate": _ratio(escalations, len(decisions)),
        "mean_reply_time_minutes": None,
        "median_reply_time_minutes": None,
        "response_time_note": "No customer-visible send timestamp is available in this offline run. Runtime latency is reported under technical performance and is not presented as customer first-reply time.",
        "customer_satisfaction_proxy": {
            "mean_rating": mean(csat) if csat else None,
            "observed_tickets": len(csat),
            "source": "Historical ticket record only; this is not a rating of the system's new responses.",
        },
        "input_tickets_with_received_at": has_received_timestamps,
    }


def _guardrail_metrics(decisions: list[dict]) -> dict[str, Any]:
    keys = sorted({key for decision in decisions for key in decision.get("guardrail_results", {})})
    by_type = {key: sum(decision.get("guardrail_results", {}).get(key) == "block" for decision in decisions)
               for key in keys}
    generated = [d for d in decisions if d.get("answer") is not None or d.get("citations")]
    grounding_blocks = by_type.get("grounding", 0)
    citations = [citation for d in decisions for citation in d.get("citations", [])]
    valid_citations = sum(
        citation in {source["chunk_id"] for source in decision.get("sources", [])}
        for decision in decisions for citation in decision.get("citations", [])
    )
    supported_citations = sum(
        citation in {source["chunk_id"] for source in decision.get("sources", [])}
        and decision.get("guardrail_results", {}).get("grounding") == "pass"
        for decision in decisions for citation in decision.get("citations", [])
    )
    return {
        "activations_by_type": by_type,
        "private_data_detections": by_type.get("pii", 0),
        "generated_responses": len(generated),
        "automated_grounding_block_rate_proxy": _ratio(grounding_blocks, len(generated)),
        "hallucination_rate_proxy": _ratio(grounding_blocks, len(generated)),
        "citation_reference_resolution_rate": _ratio(valid_citations, len(citations)),
        "citation_accuracy_proxy": _ratio(supported_citations, len(citations)),
        "citation_count": len(citations),
        "valid_citation_count": valid_citations,
        "note": "Grounding and citation rates are automated validation proxies; human review is required to establish hallucination and citation accuracy.",
    }


def evaluate(input_path: Path, output_dir: Path) -> dict[str, Any]:
    tickets = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(tickets, list):
        raise ValueError("Input must be a JSON list of tickets")
    output_dir.mkdir(parents=True, exist_ok=True)
    service = SupportService()
    decisions = [service.process(ticket).to_dict() for ticket in tickets]
    (output_dir / "decisions.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")

    actions = Counter(d["action"] for d in decisions)
    latencies = [float(d["latency_ms"]) for d in decisions]
    logged = sum(d["decision_id"] is not None for d in decisions)
    expected_routes = [_labels(ticket).get("expected_route") for ticket in tickets]
    route_rows = [(expected, decision["action"]) for expected, decision in zip(expected_routes, decisions) if expected]
    route_accuracy = _ratio(sum(
        expected == ("escalate" if actual == "block" else actual)
        for expected, actual in route_rows
    ), len(route_rows))

    segments: dict[str, dict[str, dict[str, float | int]]] = {}
    for field in ("customer_tier", "customer_region", "language_fluency"):
        groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
        for ticket, decision in zip(tickets, decisions):
            groups[str(_mapping(ticket).get(field) or "unknown")].append((ticket, decision))
        segments[field] = {
            name: {
                "count": len(rows),
                "auto_response_rate": _ratio(sum(d["action"] == "auto_respond" for _, d in rows), len(rows)),
                "historical_fcr_rate": _ratio(
                    sum(bool(_history(t).get("first_contact_resolution")) for t, _ in rows
                        if isinstance(_history(t).get("first_contact_resolution"), bool)),
                    sum(isinstance(_history(t).get("first_contact_resolution"), bool) for t, _ in rows),
                ),
            }
            for name, rows in groups.items()
        }
        known_group_rates = [group["historical_fcr_rate"] for group in segments[field].values()
                             if group["historical_fcr_rate"] is not None]
        auto_rates = [group["auto_response_rate"] for group in segments[field].values()
                      if group["auto_response_rate"] is not None]
        segments[field]["quality_variation"] = {
            "historical_fcr_range_percentage_points": (max(known_group_rates) - min(known_group_rates)) * 100
            if len(known_group_rates) >= 2 else None,
            "auto_response_rate_range_percentage_points": (max(auto_rates) - min(auto_rates)) * 100
            if len(auto_rates) >= 2 else None,
            "groups_with_historical_fcr": len(known_group_rates),
            "note": "Historical outcomes and routing coverage are not substitutes for human-rated response quality.",
        }

    report = {
        "input_file": input_path.name,
        "volume": {
            "processed": len(decisions), "answered_automatically": actions["auto_respond"],
            "escalated": actions["escalate"], "blocked_by_guardrails": actions["block"],
        },
        "business": _business_metrics(decisions, tickets),
        "technical": {
            "intent_classification": _classification_metrics(decisions, tickets),
            "intent_confidence_calibration": _confidence_calibration(decisions, tickets),
            "urgency_accuracy": _ratio(
                sum(d["prediction"]["urgency"] == _labels(t).get("urgency") for d, t in zip(decisions, tickets)
                    if _labels(t).get("urgency")),
                sum(bool(_labels(t).get("urgency")) for t in tickets),
            ),
            "expected_document_retrieval": _retrieval_metrics(decisions, tickets),
            "route_accuracy_against_labels": {"accuracy": route_accuracy, "labeled_tickets": len(route_rows)},
            "latency_ms": {"mean": mean(latencies) if latencies else 0.0,
                           "median": median(latencies) if latencies else 0.0,
                           "p95": percentile(latencies, .95)},
        },
        "governance": {
            "decisions_logged": logged,
            "log_coverage": _ratio(logged, len(decisions)) if decisions else 1.0,
            "guardrails": _guardrail_metrics(decisions),
            "fairness_segments": segments,
        },
        "limitations": [
            "Offline processing latency is not customer-visible time to first reply.",
            "Historical first-contact resolution and satisfaction fields are dataset proxies, not outcomes observed in a live deployment.",
            "Automated lexical grounding checks do not replace independent human review of at least 50 responses by two assessors.",
            "Per-class scores are meaningful only where the input includes intent labels; unseen assessment inputs may omit them.",
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CloudServe support evaluation unattended")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
