import os
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider Configuration
    # Supported: "openai", "anthropic", "google", "ollama", "openai-compatible"
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_TEMPERATURE: float = 0.0

    # Provider-Specific Fallbacks
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Server Monitoring Thresholds (Percentage)
    CPU_WARNING_THRESHOLD: float = 70.0
    CPU_CRITICAL_THRESHOLD: float = 90.0
    MEMORY_WARNING_THRESHOLD: float = 80.0
    MEMORY_CRITICAL_THRESHOLD: float = 95.0
    DISK_WARNING_THRESHOLD: float = 80.0
    DISK_CRITICAL_THRESHOLD: float = 95.0

    # Security Allowlists (* = permit all non-system containers, or provide explicit list)
    ALLOWED_CONTAINERS: Union[List[str], str] = ["*"]
    ALLOWED_SERVICES: Union[List[str], str] = ["cron", "docker", "ssh"]

    # Critical Agent System Containers (Protected from self-modification)
    SYSTEM_PROTECTED_CONTAINERS: List[str] = [
        "sysadmin-backend",
        "sysadmin-dashboard",
        "sysadmin-ollama",
    ]

    # Action Approval Security
    APPROVAL_EXPIRATION_SECONDS: int = 300

    # SQLite Database Path
    DATABASE_URL: str = "sqlite:///./sysadmin_ai.db"

    # Host Observability (Docker volume mounts)
    HOST_PROC: Optional[str] = None
    HOST_SYS: Optional[str] = None

    @field_validator("ALLOWED_CONTAINERS", "ALLOWED_SERVICES", mode="before")
    @classmethod
    def parse_comma_separated_list(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def get_api_key(self) -> Optional[str]:
        """Resolves the appropriate API key based on provider."""
        if self.LLM_API_KEY:
            return self.LLM_API_KEY
        provider = self.LLM_PROVIDER.lower()
        if provider == "openai":
            return self.OPENAI_API_KEY
        elif provider in ("anthropic", "claude"):
            return self.ANTHROPIC_API_KEY
        elif provider in ("google", "gemini"):
            return self.GOOGLE_API_KEY or self.GEMINI_API_KEY
        return None


settings = Settings()
