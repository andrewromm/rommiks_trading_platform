"""ByBit exchange client wrapper using ccxt async."""

from types import TracebackType

import ccxt.async_support as ccxt

from src.core.config import settings
from src.core.logger import get_logger

log = get_logger("collector.exchange")


class ExchangeClient:
    """Async ByBit exchange client via ccxt."""

    def __init__(self) -> None:
        options: dict = {
            "defaultType": "spot",
        }
        if settings.bybit_testnet:
            options["sandboxMode"] = True

        self._exchange = ccxt.bybit(
            {
                "apiKey": settings.bybit_api_key or None,
                "secret": settings.bybit_api_secret or None,
                "options": options,
                "enableRateLimit": True,
            }
        )

    async def __aenter__(self) -> "ExchangeClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._exchange.close()

    async def fetch_markets(self) -> list[dict]:
        """Fetch all markets from ByBit."""
        return await self._exchange.fetch_markets()

    async def fetch_tickers(self, symbols: list[str] | None = None) -> dict:
        """Fetch tickers for given symbols or all."""
        return await self._exchange.fetch_tickers(symbols)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: int | None = None,
        limit: int = 200,
    ) -> list[list]:
        """Fetch OHLCV candles.

        Returns list of [timestamp_ms, open, high, low, close, volume].
        """
        return await self._exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=since, limit=limit
        )

    @property
    def rate_limit(self) -> int:
        """Rate limit in milliseconds."""
        return self._exchange.rateLimit
