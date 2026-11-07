from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


from sklearn.feature_extraction.text import TfidfVectorizer

from .schemas import SourcePassage
from .chunking import split_fixed_characters


class DocumentationRetriever:
    """Chroma-backed vector index with a deterministic local fallback."""
    def __init__(self, documentation_path: Path, threshold: float = 0.08,
                 chroma_path: Path | None = None, chunk_size: int = 800,
                 chunk_overlap: int = 120):
        self.threshold = threshold
        raw_documents = documentation_path.read_text(encoding="utf-8")
        docs = json.loads(raw_documents)
        self.passages: list[SourcePassage] = []
        for document in docs:
            sections = split_fixed_characters(document["content"], chunk_size, chunk_overlap)
            for index, section in enumerate(sections):
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
            client = chromadb.PersistentClient(path=str(chroma_path or Path("runtime/chroma")))
            collection_fingerprint = f"{raw_documents}|fixed-{chunk_size}-{chunk_overlap}"
            corpus_key = sha256(collection_fingerprint.encode("utf-8")).hexdigest()[:12]
            self.collection = client.get_or_create_collection(
                f"cloudserve_docs_{corpus_key}", embedding_function=None
            )
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
