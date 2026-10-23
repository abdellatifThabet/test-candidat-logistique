from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    warehouse_base_url: str = "http://127.0.0.1:9000"
    warehouse_timeout_seconds: float = 3.0

    max_attempts: int = 5
    retry_base_delay_seconds: float = 1.0
    dispatch_interval_seconds: float = 1.0

    database_url: str = "sqlite:///./order_relay.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()