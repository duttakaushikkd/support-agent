from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Float, Integer, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .schemas import DecisionResult, NormalizedTicket


class Base(DeclarativeBase):
    pass


class DecisionLog(Base):
    __tablename__ = "decision_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_summary: Mapped[str] = mapped_column(Text)
    prediction_json: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text)
    threshold_applied: Mapped[float] = mapped_column(Float)
    action_taken: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    guardrail_results_json: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(32), default="generation-v1")
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requirement_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    latency_ms: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DecisionStore:
    def __init__(self, database_url: str):
        if database_url.startswith("sqlite:///"):
            Path(database_url.removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self._migrate_existing_sqlite_logs()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def _migrate_existing_sqlite_logs(self) -> None:
        """Add audit fields to databases created by earlier project versions."""
        if self.engine.dialect.name != "sqlite":
            return
        columns = {column["name"] for column in inspect(self.engine).get_columns("decision_log")}
        additions = {
            "channel": "VARCHAR(32)",
            "stage": "VARCHAR(32)",
            "model_name": "VARCHAR(128)",
            "model_version": "VARCHAR(128)",
        }
        with self.engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE decision_log ADD COLUMN {name} {sql_type}")

    def save(self, ticket: NormalizedTicket, result: DecisionResult, threshold: float,
             model_name: str = "unknown", model_version: str = "support-pipeline-v1") -> int:
        from datetime import datetime, timezone
        entry = DecisionLog(
            ticket_id=ticket.ticket_id, timestamp=datetime.now(timezone.utc).isoformat(),
            channel=ticket.channel, stage="routing",
            input_summary=json.dumps(ticket.to_dict(), ensure_ascii=False), prediction_json=json.dumps({
                **result.prediction.__dict__,
                "model": {"name": model_name, "version": model_version},
                "models": {
                    "classifier": "scikit-learn TfidfVectorizer + calibrated LogisticRegression",
                    "generator": model_name,
                },
                "prompt_version": "generation-v1",
                "requirement_ids": ["FR-INGEST", "FR-CLASSIFY", "FR-RETRIEVE", "FR-ROUTE",
                                    "FR-GENERATE", "FR-VALIDATE", "FR-LOG", "FR-EVALUATE"],
            }),
            sources_json=json.dumps([source.to_dict() for source in result.sources]),
            threshold_applied=threshold, action_taken=result.action,
            reason=(result.reason + (f" | escalation summary: {result.escalation_summary}"
                                     if result.escalation_summary else "")),
            guardrail_results_json=json.dumps(result.guardrail_results),
            prompt_version="generation-v1",
            model_name=model_name, model_version=model_version,
            requirement_ids_json=json.dumps(["FR-INGEST", "FR-CLASSIFY", "FR-RETRIEVE", "FR-ROUTE",
                                             "FR-GENERATE", "FR-VALIDATE", "FR-LOG", "FR-EVALUATE"]),
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
