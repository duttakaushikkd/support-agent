from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen

from src.config import Settings


def main() -> int:
    settings = Settings.from_env()
    if not settings.llm_api_key:
        print("No provider key configured. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env first.")
        return 2
    body = json.dumps({
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": "Reply with the single word ready."}],
        "temperature": 0,
        "max_tokens": 16,
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.llm_provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/cloudserve/support-agent"
        headers["X-Title"] = "CloudServe Support Automation setup check"
    request = Request(settings.llm_base_url or "", data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        message = result["choices"][0]["message"]["content"]
        if not isinstance(message, str) or not message.strip():
            raise ValueError("provider returned an empty message")
    except Exception as exc:
        print(f"Provider check failed ({type(exc).__name__}); credential contents were not printed.",
              file=sys.stderr)
        return 1
    print(f"Provider check passed ({settings.llm_provider}, model={settings.llm_model}).")
    print(message.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
