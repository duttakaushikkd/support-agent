from __future__ import annotations

try:
    from prometheus_client import Counter, Histogram
    PROCESSED = Counter("support_tickets_processed_total", "Tickets processed", ["channel", "action"])
    LATENCY = Histogram("support_ticket_latency_seconds", "End-to-end ticket latency")
    GUARDRAIL_BLOCKS = Counter("support_guardrail_blocks_total", "Blocked responses by guardrail", ["guardrail"])
    CONFIDENCE = Histogram(
        "support_prediction_confidence",
        "Ticket classifier confidence distribution",
        ["prediction"],
        buckets=(0.2, 0.4, 0.55, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
    )
except ImportError:  # Allows non-monitoring environments to run the core service.
    PROCESSED = LATENCY = GUARDRAIL_BLOCKS = CONFIDENCE = None


def observe(action: str, latency_ms: float, channel: str = "unknown",
            guardrails: dict[str, str] | None = None,
            intent_confidence: float | None = None,
            urgency_confidence: float | None = None) -> None:
    if PROCESSED:
        PROCESSED.labels(channel=channel, action=action).inc()
        LATENCY.observe(latency_ms / 1000)
        for name, status in (guardrails or {}).items():
            if status == "block":
                GUARDRAIL_BLOCKS.labels(guardrail=name).inc()
        if intent_confidence is not None:
            CONFIDENCE.labels(prediction="intent").observe(max(0.0, min(1.0, intent_confidence)))
        if urgency_confidence is not None:
            CONFIDENCE.labels(prediction="urgency").observe(max(0.0, min(1.0, urgency_confidence)))
