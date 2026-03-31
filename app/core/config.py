from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOTESOUND_", extra="ignore")

    app_name: str = "notesound"
    api_prefix: str = "/v1"
    database_url: str = f"sqlite:///{BASE_DIR / 'notesound.db'}"
    artifacts_dir: Path = BASE_DIR / "data" / "artifacts"
    max_upload_size_bytes: int = 10 * 1024 * 1024
    max_image_dimension: int = 4096
    allowed_image_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
    omr_engine: str = "homr"
    homr_binary: str = "homr"
    job_poll_interval_ms: int = Field(default=500)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return settings

