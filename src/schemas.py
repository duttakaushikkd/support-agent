from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


Action = Literal["auto_respond", "escalate", "block"]


@dataclass
class NormalizedTicket:
    ticket_id: str
    channel: str
    subject: str
    body: str
    customer_id: str | None = None
    customer_name: str | None = None
    customer_tier: str | None = None
    customer_region: str | None = None
    language_fluency: str | None = None
    labels: dict[str, Any] | None = None
    history: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}".strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Prediction:
    intent: str
    urgency: str
    confidence: float
    alternatives: list[dict[str, float | str]]


@dataclass
class SourcePassage:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionResult:
    ticket_id: str
    action: Action
    reason: str
    prediction: Prediction
    sources: list[SourcePassage]
    answer: str | None
    citations: list[str]
    escalation_summary: str | None
    guardrail_results: dict[str, str]
    latency_ms: float
    error: str | None = None
    decision_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id, "action": self.action, "reason": self.reason,
            "prediction": asdict(self.prediction), "sources": [s.to_dict() for s in self.sources],
            "answer": self.answer, "citations": self.citations,
            "escalation_summary": self.escalation_summary,
            "guardrail_results": self.guardrail_results, "latency_ms": self.latency_ms,
            "error": self.error, "decision_id": self.decision_id,
        }
