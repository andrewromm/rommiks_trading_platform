from src.core.config import Settings


def test_default_settings():
    s = Settings(
        postgres_password="test",
        _env_file=None,
    )
    assert s.postgres_db == "trading"
    assert s.postgres_port == 5432
    assert s.bybit_testnet is True
    assert s.environment == "development"


def test_database_url():
    s = Settings(
        postgres_user="user",
        postgres_password="pass",
        postgres_host="host",
        postgres_port=5432,
        postgres_db="db",
        _env_file=None,
    )
    assert s.database_url == "postgresql+asyncpg://user:pass@host:5432/db"
    assert s.database_url_sync == "postgresql://user:pass@host:5432/db"


def test_database_url_special_chars():
    s = Settings(
        postgres_user="user",
        postgres_password="p@ss:word/123",
        postgres_host="host",
        postgres_port=5432,
        postgres_db="db",
        _env_file=None,
    )
    assert s.database_url == "postgresql+asyncpg://user:p%40ss%3Aword%2F123@host:5432/db"
    assert s.database_url_sync == "postgresql://user:p%40ss%3Aword%2F123@host:5432/db"


def test_redis_url():
    s = Settings(
        redis_host="myredis",
        redis_port=6380,
        postgres_password="test",
        _env_file=None,
    )
    assert s.redis_url == "redis://myredis:6380/0"
