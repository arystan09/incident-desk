"""Validated process configuration."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    """Settings use a dedicated prefix; process environment overrides .env."""

    model_config = SettingsConfigDict(
        env_prefix="INCIDENT_DESK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    service_name: str = Field(default="incident-desk", min_length=1)
    environment: Literal["development", "test", "production"] = "development"

    database_url: SecretStr | None = Field(default=None, repr=False)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    database_statement_timeout_ms: int = Field(default=10000, ge=1, le=300000)
    worker_poll_seconds: float = Field(default=1, ge=0.1, le=60)
    worker_lease_seconds: int = Field(default=60, ge=5, le=300)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_retry_base_seconds: int = Field(default=2, ge=1, le=60)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
            valid = (
                url.drivername == "postgresql+psycopg"
                and bool(url.host)
                and bool(url.database)
                and (url.port is None or 1 <= url.port <= 65535)
            )
        except (ArgumentError, ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError(
                "Database URL must use postgresql+psycopg with a host and database"
            ) from None
        return value
