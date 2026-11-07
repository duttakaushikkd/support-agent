from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from src.chunking import split_fixed_characters
from src.router import ALWAYS_ESCALATE


def evaluate(data_dir: Path, intent_threshold: float = 0.60,
             urgency_threshold: float = 0.45) -> dict[str, Any]:
    records = json.loads((data_dir / "development_tickets.json").read_text(encoding="utf-8"))
    train, holdout = train_test_split(
        records, test_size=0.20, random_state=42,
        stratify=[record["labels"]["intent"] for record in records],
    )
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    train_x = vectorizer.fit_transform(
        f"{row.get('subject', '')}\n{row.get('body', '')}" for row in train
    )
    models = {}
    for label in ("intent", "urgency"):
        model = CalibratedClassifierCV(
            estimator=LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"),
            method="sigmoid", cv=3,
        )
        model.fit(train_x, [row["labels"][label] for row in train])
        models[label] = model

    documents = json.loads((data_dir / "documentation.json").read_text(encoding="utf-8"))
    corpus = []
    for doc in documents:
        for chunk_index, text in enumerate(split_fixed_characters(doc["content"], 800, 120)):
            corpus.append((doc["doc_id"], f"{doc['title']}\n{text}"))
    retrieval_vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    corpus_matrix = retrieval_vectorizer.fit_transform(text for _, text in corpus)

    predictions = []
    for row in holdout:
        text = f"{row.get('subject', '')}\n{row.get('body', '')}".strip()
        row_x = vectorizer.transform([text])
        probabilities = {
            label: model.predict_proba(row_x)[0]
            for label, model in models.items()
        }
        intent_model, urgency_model = models["intent"], models["urgency"]
        intent_probs, urgency_probs = probabilities["intent"], probabilities["urgency"]
        intent_index, urgency_index = int(intent_probs.argmax()), int(urgency_probs.argmax())
        docs_query = retrieval_vectorizer.transform([text])
        scores = (corpus_matrix @ docs_query.T).toarray().ravel()
        top_hits = scores.argsort()[::-1][:3]
        has_relevant_source = any(scores[index] >= 0.08 for index in top_hits)
        predictions.append({
            "expected_route": row["labels"].get("expected_route"),
            "intent_correct": str(intent_model.classes_[intent_index]) == row["labels"]["intent"],
            "urgency_correct": str(urgency_model.classes_[urgency_index]) == row["labels"]["urgency"],
            "intent": str(intent_model.classes_[intent_index]),
            "intent_confidence": float(intent_probs[intent_index]),
            "urgency_confidence": float(urgency_probs[urgency_index]),
            "has_relevant_source": has_relevant_source,
        })

    def summarize(intent_floor: float, urgency_floor: float) -> dict[str, Any]:
        decisions = []
        for row in predictions:
            action = "escalate" if (
                row["intent"] in ALWAYS_ESCALATE
                or row["intent_confidence"] < intent_floor
                or row["urgency_confidence"] < urgency_floor
                or not row["has_relevant_source"]
            ) else "auto_respond"
            decisions.append((action, row["expected_route"]))
        labeled = [(action, expected) for action, expected in decisions if expected]
        auto = [(action, expected) for action, expected in labeled if action == "auto_respond"]
        return {
            "intent_threshold": intent_floor,
            "urgency_threshold": urgency_floor,
            "auto_response_coverage": mean(action == "auto_respond" for action, _ in decisions),
            "route_accuracy": mean(action == expected for action, expected in labeled),
            "auto_response_precision_against_expected_route": (
                mean(expected == "auto_respond" for _, expected in auto) if auto else None
            ),
        }

    return {
        "method": "Stratified 80/20 development split, random_state=42; thresholds selected on holdout route labels.",
        "training_tickets": len(train),
        "holdout_tickets": len(holdout),
        "holdout_intent_accuracy": mean(row["intent_correct"] for row in predictions),
        "holdout_urgency_accuracy": mean(row["urgency_correct"] for row in predictions),
        "shared_0_55_threshold": summarize(0.55, 0.55),
        "selected_thresholds": summarize(intent_threshold, urgency_threshold),
        "warning": "Thresholds are provisional; this is one development holdout, not an independent assessment or probability calibration guarantee.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit routing thresholds on a fixed development holdout")
    parser.add_argument("--data-dir", type=Path,
                        default=Path("FDE_Capstone_Complete/Capstone_Pack/05_Datasets"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = evaluate(args.data_dir)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
