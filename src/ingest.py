from __future__ import annotations

from typing import Any

from .schemas import NormalizedTicket

VALID_CHANNELS = {"email", "chat", "docs_comment", "forum"}


def normalize_ticket(raw: dict[str, Any]) -> NormalizedTicket:
    if not isinstance(raw, dict):
        raise ValueError("Ticket must be a JSON object")
    ticket_id = str(raw.get("ticket_id") or "unknown-ticket")
    channel = str(raw.get("channel") or "unknown")
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Unsupported channel: {channel}")
    return NormalizedTicket(
        ticket_id=ticket_id, channel=channel, subject=str(raw.get("subject") or ""),
        body=str(raw.get("body") or ""), customer_id=raw.get("customer_id"),
        customer_name=raw.get("customer_name"), customer_tier=raw.get("customer_tier"),
        customer_region=raw.get("customer_region"), language_fluency=raw.get("language_fluency"),
        labels=raw.get("labels") if isinstance(raw.get("labels"), dict) else None,
        history=raw.get("history") if isinstance(raw.get("history"), dict) else None,
    )
