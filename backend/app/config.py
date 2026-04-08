from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_CANDIDATES = [_BACKEND_DIR / ".env", _REPO_ROOT / ".env"]
_ENV_FILES = tuple(str(p) for p in _ENV_CANDIDATES if p.is_file())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES if _ENV_FILES else (".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    review_timeout_sec: int = 120

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    java_home: str = Field(
        default="",
        validation_alias="JAVA_HOME",
        description="JDK root for Java sandbox host fallback (optional)",
    )

    max_code_bytes: int = 100_000
    max_stdin_bytes: int = 16_384
    max_output_bytes: int = 64_000

    sandbox_enabled: bool = True
    sandbox_image: str = "cellebrite-code-sandbox:local"
    sandbox_timeout_sec: int = 15
    sandbox_memory_mb: int = 256
    sandbox_cpus: float = 1.0


def get_settings() -> Settings:
    return Settings()
