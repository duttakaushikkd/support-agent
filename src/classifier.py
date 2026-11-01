from __future__ import annotations

import json
from pathlib import Path

from sklearn.calibration import CalibratedClassifierCV
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
        # Cross-validated sigmoid calibration makes the routing score more
        # interpretable than the raw maximum probability from an uncalibrated
        # logistic model. The fixed seed keeps training reproducible.
        self.intent_model = CalibratedClassifierCV(
            estimator=LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"),
            method="sigmoid", cv=3,
        )
        self.urgency_model = CalibratedClassifierCV(
            estimator=LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"),
            method="sigmoid", cv=3,
        )
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
            urgency_probabilities = self.urgency_model.predict_proba(vector)[0]
            urgency_index = int(urgency_probabilities.argmax())
            urgency = str(self.urgency_model.classes_[urgency_index])
            urgency_alternatives = [
                {"value": str(self.urgency_model.classes_[index]),
                 "confidence": round(float(urgency_probabilities[index]), 4)}
                for index in urgency_probabilities.argsort()[::-1]
            ]
            return Prediction(intent, urgency, round(float(probabilities[ranked[0]]), 4), alternatives,
                              round(float(urgency_probabilities[urgency_index]), 4), urgency_alternatives)
        except Exception:
            return Prediction("unclear_request", "medium", 0.0, [])
