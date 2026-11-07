from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from src.chunking import split_fixed_characters, split_markdown_sections


def _corpus_chunks(documents: list[dict[str, Any]], strategy: str) -> list[tuple[str, str, str]]:
    chunks = []
    for document in documents:
        if strategy == "markdown_sections":
            content_chunks = split_markdown_sections(document["content"])
        elif strategy == "fixed_800_120":
            content_chunks = split_fixed_characters(document["content"], 800, 120)
        else:
            raise ValueError(f"Unsupported chunk strategy: {strategy}")
        chunks.extend((f"{document['doc_id']}:{index}", document["doc_id"], text)
                      for index, text in enumerate(content_chunks))
    return chunks


def evaluate_strategy(tickets: list[dict[str, Any]], documents: list[dict[str, Any]],
                      strategy: str, top_k: int = 3, threshold: float = 0.08) -> dict[str, Any]:
    chunks = _corpus_chunks(documents, strategy)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    matrix = vectorizer.fit_transform([f"{doc_id}\n{text}" for _, doc_id, text in chunks])
    eligible = 0
    hit_at_1 = hit_at_k = 0
    reciprocal_ranks = []
    for ticket in tickets:
        labels = ticket.get("labels") or {}
        expected = set(labels.get("expected_doc_ids") or [])
        if not labels.get("answerable_from_docs", bool(expected)) or not expected:
            continue
        eligible += 1
        query = f"{ticket.get('subject', '')}\n{ticket.get('body', '')}"
        scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
        ranked = [index for index in scores.argsort()[::-1] if scores[index] >= threshold][:top_k]
        ranked_doc_ids = [chunks[index][1] for index in ranked]
        hit_at_1 += bool(ranked_doc_ids[:1] and expected.intersection(ranked_doc_ids[:1]))
        hit_at_k += bool(expected.intersection(ranked_doc_ids))
        rank = next((index + 1 for index, doc_id in enumerate(ranked_doc_ids) if doc_id in expected), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {
        "strategy": strategy,
        "chunk_count": len(chunks),
        "mean_chunk_characters": mean(len(text) for _, _, text in chunks) if chunks else 0,
        "eligible_tickets": eligible,
        "threshold": threshold,
        "top_1_expected_document_hit_rate": hit_at_1 / eligible if eligible else None,
        "top_k": top_k,
        "top_k_expected_document_hit_rate": hit_at_k / eligible if eligible else None,
        "mean_reciprocal_rank_at_k": mean(reciprocal_ranks) if reciprocal_ranks else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare retrieval chunking on development labels")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tickets = json.loads((args.data_dir / "development_tickets.json").read_text(encoding="utf-8"))
    documents = json.loads((args.data_dir / "documentation.json").read_text(encoding="utf-8"))
    result = {
        "data": "development_tickets.json (development only; not the hidden set)",
        "strategies": [
            evaluate_strategy(tickets, documents, "markdown_sections"),
            evaluate_strategy(tickets, documents, "fixed_800_120"),
        ],
        "interpretation_note": "Document-ID retrieval hit on labeled answerable tickets is a retrieval proxy, not answer correctness. Keep one chunking strategy based on this comparison and do not tune against hidden assessment data.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
