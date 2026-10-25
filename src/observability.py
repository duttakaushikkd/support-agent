from __future__ import annotations

try:
    from prometheus_client import Counter, Histogram
    PROCESSED = Counter("support_tickets_processed_total", "Tickets processed", ["action"])
    LATENCY = Histogram("support_ticket_latency_seconds", "End-to-end ticket latency")
except ImportError:  # Allows non-monitoring environments to run the core service.
    PROCESSED = LATENCY = None


def observe(action: str, latency_ms: float) -> None:
    if PROCESSED:
        PROCESSED.labels(action=action).inc()
        LATENCY.observe(latency_ms / 1000)
