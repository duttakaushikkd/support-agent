from __future__ import annotations

import json
import re
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        return (f"{self.settings.llm_provider}:{self.settings.llm_model}"
                if self.provider_enabled else "deterministic-local-fallback")

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
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", excerpt) if part.strip()]
        answer = " ".join(f"{sentence} [{source.chunk_id}]" for sentence in sentences)
        return answer, [source.chunk_id]

    def _provider_answer(self, ticket: NormalizedTicket, sources: list[SourcePassage]) -> tuple[str, list[str]]:
        allowed_ids = [source.chunk_id for source in sources]
        context = "\n\n".join(f"[{source.chunk_id}] {source.text}" for source in sources)
        request_body = json.dumps({
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"CUSTOMER TICKET:\n{ticket.text}\n\nSOURCE PASSAGES:\n{context}\n\n"
                    f"ALLOWED CITATIONS: {allowed_ids}"
                )},
            ],
            "temperature": 0,
            "max_tokens": 700,
        }).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.settings.llm_provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/cloudserve/support-agent"
            headers["X-Title"] = "CloudServe Support Automation"
        request = Request(self.settings.llm_base_url or "", data=request_body, headers=headers, method="POST")

        # Retry one transient rate-limit or server error, then fall back locally.
        for attempt in range(2):
            try:
                with urlopen(request, timeout=12.0) as response:
                    completion = json.loads(response.read().decode("utf-8"))
                content = completion["choices"][0]["message"]["content"]
                payload = self._parse_model_json(str(content or ""))
                answer = str(payload.get("answer", "")).strip()
                citations = [str(value) for value in payload.get("citations", []) if str(value) in allowed_ids]
                if answer and citations:
                    return answer, citations
                raise ValueError("Provider response did not contain a grounded answer")
            except HTTPError as exc:
                if attempt == 0 and (exc.code == 429 or exc.code >= 500):
                    sleep(0.5)
                    continue
                raise
            except URLError:
                if attempt == 0:
                    sleep(0.5)
                    continue
                raise
        raise RuntimeError("unreachable")

    @staticmethod
    def _parse_model_json(content: str) -> dict:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("Provider response was not a JSON object")
            payload = json.loads(cleaned[start:end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Provider response was not a JSON object")
        return payload
