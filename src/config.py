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
        project_root = Path(__file__).resolve().parents[1]
        configured_data_dir = os.getenv("DATA_DIR")
        if configured_data_dir:
            data_dir = Path(configured_data_dir).expanduser()
            if not data_dir.is_absolute():
                data_dir = project_root / data_dir
        else:
            candidates = (
                project_root / "Capstone_Pack/05_Datasets",
                project_root / "FDE_Capstone_Complete/Capstone_Pack/05_Datasets",
                project_root / "tests/fixtures",
            )
            data_dir = next((path for path in candidates if (path / "development_tickets.json").exists()), candidates[0])
        return cls(
            data_dir=data_dir,
            database_url=os.getenv("DATABASE_URL", "sqlite:///runtime/support_agent.db"),
            auto_response_threshold=float(os.getenv("AUTO_RESPONSE_THRESHOLD", "0.55")),
            retrieval_threshold=float(os.getenv("RETRIEVAL_THRESHOLD", "0.08")),
            llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )
