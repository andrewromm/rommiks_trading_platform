from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "trading"
    postgres_user: str = "trading"
    postgres_password: str = "changeme"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # ByBit
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Sentiment
    lunarcrush_api_key: str = ""
    whale_alert_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # OpenClaw
    openclaw_webhook_secret: str = ""

    # General
    log_level: str = "INFO"
    environment: str = "development"

    @property
    def _db_credentials(self) -> str:
        return f"{quote_plus(self.postgres_user)}:{quote_plus(self.postgres_password)}"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self._db_credentials}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self._db_credentials}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
