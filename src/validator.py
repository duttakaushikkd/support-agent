from __future__ import annotations

import re

from .schemas import NormalizedTicket, SourcePassage

PII_PATTERNS = [
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:\+?\d[\d ().-]{7,}\d)\b"),
    re.compile(r"\b(?:sk|rk|pk|api)[_-][A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
]
INJECTION_PATTERN = re.compile(
    r"ignore\s+(?:all\s+|previous\s+|the\s+)?instructions|"
    r"(?:system|developer)\s+prompt|reveal\s+(?:your\s+)?instructions|"
    r"act\s+as\s+(?:an?\s+)?(?:admin|system)", re.I,
)
COMMITMENT_PATTERN = re.compile(
    r"\b(?:refund|credit will be issued|we will resolve.*by|guarantee|"
    r"we promise|your issue will be fixed|we will compensate)\b", re.I,
)
TOKEN_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9_-]{2,}\b", re.I)
NON_CLAIM_WORDS = {
    "about", "after", "again", "also", "although", "another", "because", "before",
    "being", "below", "between", "could", "does", "during", "each", "from", "have",
    "here", "into", "more", "most", "only", "other", "please", "same", "should",
    "some", "than", "that", "their", "then", "there", "these", "they", "this",
    "those", "through", "under", "until", "using", "when", "where", "which", "while",
    "with", "would", "your", "cloudserve", "based", "documentation", "source",
}
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")


def _sensitive_data_in_answer(answer: str, ticket: NormalizedTicket) -> bool:
    if any(pattern.search(answer) for pattern in PII_PATTERNS):
        return True
    # Do not repeat the submitter's identifying fields or sensitive strings
    # from their ticket in an outbound answer.
    private_values = [ticket.customer_id, ticket.customer_name]
    private_values.extend(match.group(0) for pattern in PII_PATTERNS for match in pattern.finditer(ticket.text))
    lowered_answer = answer.casefold()
    return any(value and len(str(value).strip()) >= 4 and str(value).casefold() in lowered_answer
               for value in private_values)


def _claim_tokens(text: str) -> set[str]:
    return {
        token.casefold() for token in TOKEN_PATTERN.findall(text)
        if len(token) >= 4 and token.casefold() not in NON_CLAIM_WORDS
    }


def _claims_are_supported(answer: str, citations: list[str], sources: list[SourcePassage]) -> bool:
    source_by_id = {source.chunk_id: source for source in sources}
    if not citations or not set(citations).issubset(source_by_id):
        return False
    factual_sentences = [s.strip() for s in SENTENCE_SPLIT.split(answer) if _claim_tokens(s)]
    if not factual_sentences:
        return False
    for sentence in factual_sentences:
        sentence_citations = set(CITATION_PATTERN.findall(sentence)) & set(citations)
        if not sentence_citations:
            return False
        claim_tokens = _claim_tokens(CITATION_PATTERN.sub("", sentence))
        supported = set()
        for citation in sentence_citations:
            supported.update(_claim_tokens(source_by_id[citation].text))
        # A cited ID must support a meaningful part of each claim. This is a
        # deterministic lexical check; unclear or paraphrased claims fail closed.
        if not claim_tokens or len(claim_tokens & supported) / len(claim_tokens) < 0.2:
            return False
    return True


def validate(ticket: NormalizedTicket, answer: str, citations: list[str], sources: list[SourcePassage]) -> dict[str, str]:
    results = {
        "pii": "pass",
        "grounding": "pass",
        "instruction_integrity": "pass",
        "tone_scope": "pass",
        "confidence_floor": "pass",
    }
    if _sensitive_data_in_answer(answer, ticket):
        results["pii"] = "block"
    if not _claims_are_supported(answer, citations, sources):
        results["grounding"] = "block"
    if INJECTION_PATTERN.search(ticket.text):
        results["instruction_integrity"] = "block"
    if COMMITMENT_PATTERN.search(answer):
        results["tone_scope"] = "block"
    return results
