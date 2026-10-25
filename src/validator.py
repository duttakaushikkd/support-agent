from __future__ import annotations

import re

from .schemas import NormalizedTicket, SourcePassage

PII_PATTERNS = [r"\bsk-[A-Za-z0-9_-]{12,}\b", r"\b(?:\d[ -]*?){13,16}\b"]
INJECTION_PATTERN = re.compile(r"ignore (?:all |previous |the )?instructions|system prompt|developer message", re.I)
COMMITMENT_PATTERN = re.compile(r"refund|credit will be issued|we will resolve.*by|guarantee", re.I)


def validate(ticket: NormalizedTicket, answer: str, citations: list[str], sources: list[SourcePassage]) -> dict[str, str]:
    results = {"pii": "pass", "grounding": "pass", "instruction_integrity": "pass", "tone_scope": "pass"}
    if any(re.search(pattern, answer) for pattern in PII_PATTERNS):
        results["pii"] = "block"
    if not citations or not set(citations).issubset({source.chunk_id for source in sources}):
        results["grounding"] = "block"
    if INJECTION_PATTERN.search(ticket.text):
        results["instruction_integrity"] = "block"
    if COMMITMENT_PATTERN.search(answer):
        results["tone_scope"] = "block"
    return results
