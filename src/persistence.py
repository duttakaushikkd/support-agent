from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .schemas import DecisionResult, NormalizedTicket


class Base(DeclarativeBase):
    pass


class DecisionLog(Base):
    __tablename__ = "decision_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    input_summary: Mapped[str] = mapped_column(Text)
    prediction_json: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text)
    threshold_applied: Mapped[float] = mapped_column(Float)
    action_taken: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    guardrail_results_json: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(32), default="generation-v1")
    requirement_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    latency_ms: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DecisionStore:
    def __init__(self, database_url: str):
        if database_url.startswith("sqlite:///"):
            Path(database_url.removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def save(self, ticket: NormalizedTicket, result: DecisionResult, threshold: float) -> int:
        from datetime import datetime, timezone
        entry = DecisionLog(
            ticket_id=ticket.ticket_id, timestamp=datetime.now(timezone.utc).isoformat(),
            input_summary=ticket.text[:1000], prediction_json=json.dumps(result.prediction.__dict__),
            sources_json=json.dumps([source.to_dict() for source in result.sources]),
            threshold_applied=threshold, action_taken=result.action, reason=result.reason,
            guardrail_results_json=json.dumps(result.guardrail_results),
            latency_ms=result.latency_ms, error=result.error,
        )
        with self.session_factory() as session:
            session.add(entry)
            session.commit()
            return int(entry.id)

    def count(self) -> int:
        from sqlalchemy import func, select
        with self.session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(DecisionLog)) or 0)
