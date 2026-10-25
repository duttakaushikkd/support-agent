from __future__ import annotations

import json
import re
from pathlib import Path


from sklearn.feature_extraction.text import TfidfVectorizer

from .schemas import SourcePassage


class DocumentationRetriever:
    """Chroma-backed vector index with a deterministic local fallback."""
    def __init__(self, documentation_path: Path, threshold: float = 0.08):
        self.threshold = threshold
        docs = json.loads(documentation_path.read_text())
        self.passages: list[SourcePassage] = []
        for document in docs:
            sections = re.split(r"\n(?=#+\s|\d+\.\s)", document["content"])
            for index, section in enumerate(s for s in sections if s.strip()):
                self.passages.append(SourcePassage(
                    chunk_id=f"{document['doc_id']}:{index}", doc_id=document["doc_id"],
                    title=document["title"], text=section.strip(), score=0.0,
                ))
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        self.matrix = self.vectorizer.fit_transform([f"{p.title}\n{p.text}" for p in self.passages])
        self.collection = None
        try:
            # Store the explicitly computed vectors, avoiding a model download at service startup.
            import chromadb
            client = chromadb.PersistentClient(path="runtime/chroma")
            self.collection = client.get_or_create_collection("cloudserve_documentation", embedding_function=None)
            self.collection.upsert(
                ids=[p.chunk_id for p in self.passages], documents=[p.text for p in self.passages],
                metadatas=[{"doc_id": p.doc_id, "title": p.title} for p in self.passages],
                embeddings=self.matrix.toarray().tolist(),
            )
        except Exception:
            # Evaluation remains self-contained if Chroma is unavailable or cannot initialize.
            self.collection = None

    def search(self, query: str, limit: int = 3) -> list[SourcePassage]:
        if not query.strip():
            return []
        query_vector = self.vectorizer.transform([query])
        scores = (self.matrix @ query_vector.T).toarray().ravel()
        ranked = scores.argsort()[::-1]
        if self.collection is not None:
            try:
                hits = self.collection.query(query_embeddings=query_vector.toarray().tolist(), n_results=limit)
                ids = hits.get("ids", [[]])[0]
                index_by_id = {passage.chunk_id: i for i, passage in enumerate(self.passages)}
                ranked = [index_by_id[chunk_id] for chunk_id in ids if chunk_id in index_by_id]
            except Exception:
                pass
        results = []
        for index in ranked[:limit]:
            score = float(scores[index])
            if score < self.threshold:
                continue
            p = self.passages[int(index)]
            results.append(SourcePassage(p.chunk_id, p.doc_id, p.title, p.text, round(score, 4)))
        return results
