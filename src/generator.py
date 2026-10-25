from __future__ import annotations

import json
from pathlib import Path
from time import sleep

from .config import Settings
from .schemas import NormalizedTicket, SourcePassage


class AnswerGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider_enabled = bool(settings.llm_api_key)
        self.prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "generation_v1.md"
        self.system_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        if not self.system_prompt:
            raise ValueError(f"Generation prompt is empty: {self.prompt_path}")

    @property
    def model_name(self) -> str:
        return self.settings.llm_model if self.provider_enabled else "deterministic-local-fallback"

    def generate(self, ticket: NormalizedTicket, sources: list[SourcePassage]) -> tuple[str, list[str]]:
        if self.provider_enabled:
            try:
                return self._provider_answer(ticket, sources)
            except Exception:
                # Model availability must never terminate a ticket or batch run.
                pass
        return self._fallback_answer(sources)

    def _fallback_answer(self, sources: list[SourcePassage]) -> tuple[str, list[str]]:
        """Deterministic grounded fallback keeps evaluation runnable without a provider."""
        source = sources[0]
        excerpt = " ".join(source.text.replace("#", "").split())[:700]
        answer = f"Based on CloudServe documentation: {excerpt}\n\nSource: [{source.chunk_id}]"
        return answer, [source.chunk_id]

    def _provider_answer(self, ticket: NormalizedTicket, sources: list[SourcePassage]) -> tuple[str, list[str]]:
        from openai import OpenAI

        allowed_ids = [source.chunk_id for source in sources]
        context = "\n\n".join(f"[{source.chunk_id}] {source.text}" for source in sources)
        client = OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url, timeout=12.0, max_retries=0)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"CUSTOMER TICKET:\n{ticket.text}\n\nSOURCE PASSAGES:\n{context}\n\nALLOWED CITATIONS: {allowed_ids}"},
        ]
        # A short bounded retry handles free-tier transient rate limits without blocking a run.
        for attempt in range(2):
            try:
                response = client.chat.completions.create(model=self.settings.llm_model, messages=messages, response_format={"type": "json_object"})
                payload = json.loads(response.choices[0].message.content or "{}")
                answer = str(payload.get("answer", "")).strip()
                citations = [str(value) for value in payload.get("citations", []) if str(value) in allowed_ids]
                if answer and citations:
                    return answer, citations
                raise ValueError("Provider response did not contain a grounded answer")
            except Exception:
                if attempt:
                    raise
                sleep(0.5)
        raise RuntimeError("unreachable")
