from __future__ import annotations

from .schemas import Prediction, SourcePassage

ALWAYS_ESCALATE = {
    "security_incident", "compliance_request", "feature_request", "unclear_request",
    "billing_query", "data_residency",
}


def route(prediction: Prediction, sources: list[SourcePassage], intent_threshold: float,
          urgency_threshold: float) -> tuple[str, str]:
    if prediction.intent in ALWAYS_ESCALATE:
        return "escalate", f"{prediction.intent} requires human handling by policy"
    if prediction.confidence < intent_threshold:
        return "escalate", f"intent confidence {prediction.confidence:.2f} is below threshold {intent_threshold:.2f}"
    if prediction.urgency_confidence < urgency_threshold:
        return "escalate", f"urgency confidence {prediction.urgency_confidence:.2f} is below threshold {urgency_threshold:.2f}"
    if not sources:
        return "escalate", "no documentation passage met the relevance threshold"
    return "auto_respond", "confidence and retrieval quality meet the auto-response policy"
