"""Validated process configuration."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings use a dedicated prefix; process environment overrides .env."""

    model_config = SettingsConfigDict(
        env_prefix="INCIDENT_DESK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    service_name: str = Field(default="incident-desk", min_length=1)
    environment: Literal["development", "test", "production"] = "development"
