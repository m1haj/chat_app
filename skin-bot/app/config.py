"""Application settings loaded from environment variables or .env."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "skin-bot"
    environment: str = "development"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)
    max_image_dimension: int = Field(default=1024, ge=256, le=2048)
    max_prompt_characters: int = Field(default=2000, ge=100, le=10000)
    request_timeout_seconds: float = Field(default=45.0, gt=1, le=180)
    allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()