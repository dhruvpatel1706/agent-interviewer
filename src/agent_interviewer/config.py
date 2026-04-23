"""Runtime configuration from env + .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="")
    interviewer_model: str = Field(
        default="claude-opus-4-7",
        description="Model for the interviewer persona (answering follow-ups).",
    )
    feedback_model: str = Field(
        default="claude-opus-4-7",
        description="Model for the end-of-session feedback agent.",
    )
    sessions_dir: Path = Field(
        default=Path.home() / ".agent-interviewer" / "sessions",
        description="Where session transcripts are stored as JSONL.",
    )


def get_settings() -> Settings:
    return Settings()
