from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///.runtime/flakeguard.db"
    flakeguard_api_key: SecretStr = SecretStr("")
    flakeguard_api_url: str = "http://127.0.0.1:8000"
    flakeguard_read_only: bool = False
    github_token: SecretStr = SecretStr("")
    github_repositories: str = ""
    max_report_bytes: int = 20 * 1024 * 1024
    max_archive_bytes: int = 50 * 1024 * 1024
    max_archive_files: int = 200
    max_results: int = 100_000
    http_timeout_seconds: float = 30

    @property
    def allowed_repositories(self) -> set[str]:
        return {r.strip().lower() for r in self.github_repositories.split(",") if r.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
