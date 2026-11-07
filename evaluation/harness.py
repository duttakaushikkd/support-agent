from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
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
        if isinstance(actual, str) and isinstance(predicted, str) and actual in confusion and predicted in confusion[actual]:
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
        expected = set(map(str, raw_expected)) if isinstance(raw_expected, list) else set()
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
    known_repeat = [h["repeat_contact"] for h in histories if isinstance(h.get("repeat_contact"), bool)]
    escalations = sum(d["action"] == "escalate" for d in decisions)
    auto_answers = sum(d["action"] == "auto_respond" for d in decisions)
    latencies = [float(d["latency_ms"]) for d in decisions]
    reply_minutes = []
    for ticket in tickets:
        received_at = _parse_received_at(_mapping(ticket).get("received_at"))
        reply_at = next((_parse_received_at(_mapping(ticket).get(key)) for key in
                         ("first_reply_at", "replied_at", "responded_at", "reply_at")
                         if _parse_received_at(_mapping(ticket).get(key)) is not None), None)
        if received_at and reply_at:
            try:
                reply_minutes.append((reply_at - received_at).total_seconds() / 60)
            except TypeError:
                # Mixed timezone-naive/aware values cannot be compared safely.
                continue
    return {
        "system_first_contact_resolution": {
            "rate": None,
            "note": "The offline evaluator has no post-response resolution event, so system FCR cannot be observed from this input.",
        },
        "auto_response_coverage": {
            "rate": _ratio(auto_answers, len(decisions)),
            "auto_answered_tickets": auto_answers,
            "method": "Automatic response share; this is not first-contact resolution.",
        },
        "historical_ticket_outcomes": {
            "first_contact_resolution_rate": _ratio(sum(known_fcr), len(known_fcr)) if known_fcr else None,
            "observed_tickets": len(known_fcr),
            "repeat_contact_rate": _ratio(sum(known_repeat), len(known_repeat)) if known_repeat else None,
            "repeat_contact_observed_tickets": len(known_repeat),
        },
        "escalation_rate": _ratio(escalations, len(decisions)),
        "mean_first_reply_minutes": mean(reply_minutes) if reply_minutes else None,
        "median_first_reply_minutes": median(reply_minutes) if reply_minutes else None,
        "observed_first_reply_timestamps": len(reply_minutes),
        "response_time_note": "Computed only from received_at and first_reply_at/replied_at/responded_at/reply_at timestamps. Empty when no customer-visible reply timestamps exist.",
        "customer_satisfaction_proxy": {
            "mean_rating": mean(csat) if csat else None,
            "observed_tickets": len(csat),
            "source": "Historical ticket record only; this is not a rating of the system's new responses.",
        },
        "availability": {
            "observed_percent": None,
            "target_percent": 99.5,
            "note": "Availability requires a time-based monitored service window; an offline batch run cannot establish it.",
        },
    }


def _urgency_metrics(decisions: list[dict], tickets: list[dict]) -> dict[str, Any]:
    labels = sorted({
        value for ticket, decision in zip(tickets, decisions)
        for value in (_labels(ticket).get("urgency"), decision["prediction"].get("urgency"))
        if isinstance(value, str)
    })
    confusion = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for ticket, decision in zip(tickets, decisions):
        actual = _labels(ticket).get("urgency")
        predicted = decision["prediction"].get("urgency")
        if isinstance(actual, str) and isinstance(predicted, str) and actual in confusion and predicted in confusion[actual]:
            confusion[actual][predicted] += 1
    per_class = {}
    for label in labels:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[actual][label] for actual in labels)
        precision = _ratio(tp, predicted_count)
        recall = _ratio(tp, support)
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
    total = sum(sum(row.values()) for row in confusion.values())
    correct = sum(confusion[label][label] for label in labels)
    return {"evaluated_tickets": total, "accuracy": _ratio(correct, total),
            "per_class": per_class, "confusion_matrix": confusion}


def _ground_truth_metrics(decisions: list[dict], tickets: list[dict], path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"available": False, "matched_tickets": 0,
                "note": "No ground-truth response file was found. Reference answers are never used as runtime replies."}
    records = json.loads(path.read_text(encoding="utf-8"))
    reference_by_id = {str(row.get("ticket_id")): row for row in records if isinstance(row, dict) and row.get("ticket_id")}
    matched = 0
    answered = 0
    expected_doc_eligible = 0
    expected_doc_hits = 0
    mention_obligations = 0
    mention_met = 0
    forbidden_claims = 0
    for ticket, decision in zip(tickets, decisions):
        reference = reference_by_id.get(str(_mapping(ticket).get("ticket_id", "")))
        if reference is None:
            continue
        matched += 1
        answer = decision.get("answer")
        if decision.get("action") != "auto_respond" or not isinstance(answer, str):
            continue
        answered += 1
        answer_folded = " ".join(answer.casefold().split())
        expected = reference.get("expected_doc_ids", [])
        expected = expected if isinstance(expected, list) else []
        if expected:
            expected_doc_eligible += 1
            found = {str(source.get("doc_id")) for source in decision.get("sources", []) if isinstance(source, dict)}
            expected_doc_hits += bool(set(map(str, expected)) & found)
        mentions = reference.get("must_mention", [])
        mentions = [mentions] if isinstance(mentions, str) else mentions if isinstance(mentions, list) else []
        for phrase in mentions:
            if not isinstance(phrase, str) or not phrase.strip():
                continue
            mention_obligations += 1
            mention_met += " ".join(phrase.casefold().split()) in answer_folded
        forbidden = reference.get("must_not_claim", [])
        forbidden = [forbidden] if isinstance(forbidden, str) else forbidden if isinstance(forbidden, list) else []
        if any(isinstance(phrase, str) and phrase.strip()
               and " ".join(phrase.casefold().split()) in answer_folded for phrase in forbidden):
            forbidden_claims += 1
    return {
        "available": True,
        "matched_tickets": matched,
        "auto_responses_with_reference": answered,
        "expected_document_hit_rate": _ratio(expected_doc_hits, expected_doc_eligible),
        "expected_document_eligible_answers": expected_doc_eligible,
        "must_mention_phrase_coverage": _ratio(mention_met, mention_obligations),
        "must_mention_obligations": mention_obligations,
        "answers_with_exact_must_not_claim_phrase": forbidden_claims,
        "method": "Ticket-ID join; exact normalized phrase checks for must_mention and must_not_claim. This does not assess semantic quality.",
        "reference_response_used_for_generation": False,
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


def evaluate(input_path: Path, output_dir: Path,
             ground_truth_path: Path | None = None) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    input_bytes = input_path.read_bytes()
    tickets = json.loads(input_bytes.decode("utf-8"))
    if not isinstance(tickets, list):
        raise ValueError("Input must be a JSON list of tickets")
    output_dir.mkdir(parents=True, exist_ok=True)
    service = SupportService()
    if ground_truth_path is None:
        ground_truth_path = service.settings.ground_truth_path
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
        "evaluation_metadata": {
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "tickets_in_run": len(decisions),
            "invocation_count": 1,
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "system_version": _system_version(),
            "source_sha256": _source_hash(),
            "ground_truth_file": ground_truth_path.name if ground_truth_path and ground_truth_path.exists() else None,
            "routing_thresholds": {
                "intent_confidence": service.settings.auto_response_threshold,
                "urgency_confidence": service.settings.auto_response_urgency_threshold,
            },
        },
        "volume": {
            "processed": len(decisions), "answered_automatically": actions["auto_respond"],
            "escalated": actions["escalate"], "blocked_by_guardrails": actions["block"],
        },
        "business": _business_metrics(decisions, tickets),
        "technical": {
            "intent_classification": _classification_metrics(decisions, tickets),
            "urgency_classification": _urgency_metrics(decisions, tickets),
            "intent_confidence_calibration": _confidence_calibration(decisions, tickets),
            "expected_document_retrieval": _retrieval_metrics(decisions, tickets),
            "ground_truth_response_checks": _ground_truth_metrics(decisions, tickets, ground_truth_path),
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
    parser.add_argument("--ground-truth", type=Path, default=None,
                        help="Optional ground_truth_responses.json for ticket-ID-matched response checks")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input, args.output, args.ground_truth), indent=2))


def _system_version() -> str:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        return commit + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "working-tree"


def _source_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    paths = sorted([*root.joinpath("src").glob("*.py"),
                    *root.joinpath("prompts").glob("*.md"),
                    root / "evaluation" / "harness.py"])
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    main()
