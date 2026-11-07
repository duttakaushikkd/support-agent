from __future__ import annotations

from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from fastapi.responses import HTMLResponse, Response

from .service import SupportService

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ImportError:  # pragma: no cover - the pinned requirements include the exporter.
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"
    generate_latest = None

app = FastAPI(title="CloudServe Support Automation", version="1.0.0")
service: SupportService | None = None


def get_service() -> SupportService:
    global service
    if service is None:
        service = SupportService()
    return service


class TicketRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    ticket_id: str | None = None
    channel: str
    subject: str = ""
    body: str = ""
    customer_tier: str | None = None
    customer_region: str | None = None
    language_fluency: str | None = None


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def tester_ui() -> str:
    return (Path(__file__).parent / "templates" / "index.html").read_text()


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        active = get_service()
        return {"status": "ok", "database": "ready", "retrieval": "ready", "provider": active.generator.model_name}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"service unavailable: {type(exc).__name__}")


@app.post("/ticket")
@app.post("/tickets", include_in_schema=False)
def process_ticket(ticket: TicketRequest) -> dict[str, Any]:
    """Accept a single ticket; malformed JSON values are safely logged as escalations."""
    return get_service().process(ticket.model_dump(exclude_none=True)).to_dict()


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if generate_latest is None:
        raise HTTPException(status_code=503, detail="Prometheus client is not installed")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000)
