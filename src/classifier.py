from __future__ import annotations

import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .schemas import NormalizedTicket, Prediction


class TicketClassifier:
    def __init__(self, development_path: Path):
        records = json.loads(development_path.read_text())
        texts = [f"{r.get('subject', '')}\n{r.get('body', '')}" for r in records]
        intents = [r["labels"]["intent"] for r in records]
        urgencies = [r["labels"]["urgency"] for r in records]
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        vectors = self.vectorizer.fit_transform(texts)
        self.intent_model = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
        self.urgency_model = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
        self.intent_model.fit(vectors, intents)
        self.urgency_model.fit(vectors, urgencies)

    def predict(self, ticket: NormalizedTicket) -> Prediction:
        if not ticket.text:
            return Prediction("unclear_request", "medium", 0.0, [])
        try:
            vector = self.vectorizer.transform([ticket.text])
            probabilities = self.intent_model.predict_proba(vector)[0]
            ranked = probabilities.argsort()[::-1]
            intent = str(self.intent_model.classes_[ranked[0]])
            alternatives = [
                {"value": str(self.intent_model.classes_[index]), "confidence": round(float(probabilities[index]), 4)}
                for index in ranked[:3]
            ]
            urgency = str(self.urgency_model.predict(vector)[0])
            return Prediction(intent, urgency, round(float(probabilities[ranked[0]]), 4), alternatives)
        except Exception:
            return Prediction("unclear_request", "medium", 0.0, [])
