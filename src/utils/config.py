from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_title: str = "ZenithOCR API"
    api_version: str = "1.0.0"

    # Groq
    groq_api_key: str = ""

    # OCR
    ocr_languages: str = "en,es"
    ocr_gpu: bool = False

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
