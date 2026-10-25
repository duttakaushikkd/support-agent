from __future__ import annotations

from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .service import SupportService

app = FastAPI(title="CloudServe Support Automation", version="1.0.0")
service: SupportService | None = None


def get_service() -> SupportService:
    global service
    if service is None:
        service = SupportService()
    return service


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


@app.post("/tickets")
def process_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    return get_service().process(ticket).to_dict()
