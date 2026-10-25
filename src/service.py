from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .classifier import TicketClassifier
from .config import Settings
from .generator import AnswerGenerator
from .ingest import normalize_ticket
from .observability import observe
from .persistence import DecisionStore
from .retrieval import DocumentationRetriever
from .router import route
from .schemas import DecisionResult, Prediction
from .validator import validate


class SupportService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.classifier = TicketClassifier(self.settings.data_dir / "development_tickets.json")
        self.retriever = DocumentationRetriever(
            self.settings.data_dir / "documentation.json", self.settings.retrieval_threshold
        )
        self.generator = AnswerGenerator(self.settings)
        self.store = DecisionStore(self.settings.database_url)

    def process(self, raw_ticket: dict[str, Any]) -> DecisionResult:
        started = time.perf_counter()
        ticket_id = str(raw_ticket.get("ticket_id") or "unknown-ticket") if isinstance(raw_ticket, dict) else "unknown-ticket"
        try:
            ticket = normalize_ticket(raw_ticket)
            prediction = self.classifier.predict(ticket)
            sources = self.retriever.search(ticket.text)
            action, reason = route(prediction, sources, self.settings.auto_response_threshold)
            answer: str | None = None
            citations: list[str] = []
            escalation_summary: str | None = None
            guardrails = {"pii": "not_run", "grounding": "not_run", "instruction_integrity": "not_run", "tone_scope": "not_run"}
            if action == "auto_respond":
                answer, citations = self.generator.generate(ticket, sources)
                guardrails = validate(ticket, answer, citations, sources)
                if "block" in guardrails.values():
                    action, reason = "block", "a release guardrail blocked the drafted response"
                    escalation_summary = f"Blocked {prediction.intent}; review guardrail results and sources."
                    answer = None
                else:
                    escalation_summary = None
            else:
                escalation_summary = f"Intent: {prediction.intent}. {reason}. Sources considered: " + \
                    ", ".join(source.doc_id for source in sources) if sources else f"Intent: {prediction.intent}. {reason}."
            result = DecisionResult(ticket.ticket_id, action, reason, prediction, sources, answer, citations,
                                    escalation_summary, guardrails, (time.perf_counter() - started) * 1000)
            result.decision_id = self.store.save(ticket, result, self.settings.auto_response_threshold)
        except Exception as exc:
            # Every bad input becomes a durable escalation instead of terminating a batch run.
            from .schemas import NormalizedTicket
            ticket = NormalizedTicket(ticket_id=ticket_id, channel="unknown", subject="", body="")
            result = DecisionResult(ticket_id, "escalate", "ticket could not be processed safely",
                                    Prediction("unclear_request", "medium", 0.0, []), [], None, [],
                                    "Malformed or failed ticket requires human review.", {"system": "error"},
                                    (time.perf_counter() - started) * 1000, error=f"{type(exc).__name__}: {exc}")
            result.decision_id = self.store.save(ticket, result, self.settings.auto_response_threshold)
        observe(result.action, result.latency_ms)
        return result
