"""Environment settings: no secrets or laptop-specific paths in the code."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path
    mock_llm: bool
    embedding_backend: str
    ollama_url: str
    ollama_model: str
    admin_token: str

    @classmethod
    def from_env(cls):
        return cls(
            Path(os.getenv("DATA_DIR", "runtime")),
            os.getenv("MOCK_LLM", "false").lower() == "true",
            os.getenv("EMBEDDING_BACKEND", "sentence_transformers"),
            os.getenv("OLLAMA_URL", "http://localhost:11434"),
            os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
            os.getenv("ADMIN_TOKEN", ""),
        )
