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
    llm_provider: str = "groq"
    auto_response_kill_switch_file: Path = Path("runtime/auto_response.disabled")
    chroma_path: Path = Path("runtime/chroma")
    ground_truth_path: Path | None = None
    retrieval_chunk_size: int = 800
    retrieval_chunk_overlap: int = 120

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
        kill_switch_file = Path(os.getenv("AUTO_RESPONSE_KILL_SWITCH_FILE", "runtime/auto_response.disabled")).expanduser()
        if not kill_switch_file.is_absolute():
            kill_switch_file = project_root / kill_switch_file
        chroma_path = Path(os.getenv("CHROMA_PATH", "runtime/chroma")).expanduser()
        if not chroma_path.is_absolute():
            chroma_path = project_root / chroma_path
        chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
        chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "120"))
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("CHUNK_SIZE must be positive and CHUNK_OVERLAP must be between 0 and CHUNK_SIZE")
        provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
        provider_defaults = {
            "groq": ("https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
            "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter/free"),
        }
        if provider not in provider_defaults:
            raise ValueError("LLM_PROVIDER must be either 'groq' or 'openrouter'")
        default_endpoint, default_model = provider_defaults[provider]
        provider_key = os.getenv("GROQ_API_KEY") if provider == "groq" else os.getenv("OPENROUTER_API_KEY")
        ground_truth_value = os.getenv("GROUND_TRUTH_PATH")
        if ground_truth_value:
            ground_truth_path = Path(ground_truth_value).expanduser()
            if not ground_truth_path.is_absolute():
                ground_truth_path = project_root / ground_truth_path
        else:
            ground_truth_path = next((candidate for candidate in (
                data_dir / "ground_truth_responses.json",
                data_dir / "ground_truth_response.json",
            ) if candidate.exists()), None)
        return cls(
            data_dir=data_dir,
            database_url=os.getenv("DATABASE_URL", "sqlite:///runtime/support_agent.db"),
            auto_response_threshold=float(os.getenv("AUTO_RESPONSE_THRESHOLD", "0.55")),
            retrieval_threshold=float(os.getenv("RETRIEVAL_THRESHOLD", "0.08")),
            llm_api_key=provider_key or os.getenv("LLM_API_KEY") or None,
            llm_base_url=os.getenv("LLM_BASE_URL") or default_endpoint,
            llm_model=os.getenv("LLM_MODEL") or default_model,
            llm_provider=provider,
            auto_response_kill_switch_file=kill_switch_file,
            chroma_path=chroma_path,
            ground_truth_path=ground_truth_path,
            retrieval_chunk_size=chunk_size,
            retrieval_chunk_overlap=chunk_overlap,
        )
