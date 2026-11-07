from __future__ import annotations

import re


def split_markdown_sections(content: str) -> list[str]:
    """Keep authored heading sections intact so steps remain with their context."""
    return [part.strip() for part in re.split(r"\n(?=#+\s|\d+\.\s)", content) if part.strip()]


def split_fixed_characters(content: str, chunk_size: int = 800,
                           overlap: int = 120) -> list[str]:
    """Fixed-size character windows, included as a measurable alternative."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Require chunk_size > overlap >= 0")
    text = content.strip()
    if not text:
        return []
    step = chunk_size - overlap
    chunks = [text[start:start + chunk_size].strip()
              for start in range(0, len(text), step)]
    return [chunk for chunk in chunks if chunk]
