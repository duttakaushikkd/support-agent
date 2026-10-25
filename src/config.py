from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    auto_response_threshold: float
    retrieval_threshold: float
    llm_api_key: str | None
    llm_base_url: str | None
    llm_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "Capstone_Pack/05_Datasets")),
            database_url=os.getenv("DATABASE_URL", "sqlite:///runtime/support_agent.db"),
            auto_response_threshold=float(os.getenv("AUTO_RESPONSE_THRESHOLD", "0.55")),
            retrieval_threshold=float(os.getenv("RETRIEVAL_THRESHOLD", "0.08")),
            llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )
