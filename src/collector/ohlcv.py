"""OHLCV data fetcher — historical backfill and incremental updates."""

import asyncio
from datetime import UTC, datetime, timedelta

from src.collector.exchange import ExchangeClient
from src.collector.storage import get_latest_timestamp, save_candles
from src.core.database import async_session
from src.core.logger import get_logger

log = get_logger("collector.ohlcv")

TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]

# Timeframe duration in milliseconds
TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

# Max candles per request (ByBit limit)
BATCH_SIZE = 200

# Delay between requests for the same symbol (seconds)
REQUEST_DELAY = 0.25

# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


async def backfill_symbol(
    client: ExchangeClient,
    symbol: str,
    timeframe: str,
    days: int = 90,
) -> int:
    """Backfill OHLCV data for a single symbol/timeframe.

    Loads from the latest existing candle (or `days` ago) up to now.
    Creates its own DB session per call.
    Returns total number of candles saved.
    """
    ccxt_symbol = _to_ccxt_symbol(symbol)
    tf_ms = TIMEFRAME_MS.get(timeframe)
    if not tf_ms:
        log.warning("unknown_timeframe", timeframe=timeframe)
        return 0

    # Determine start point
    async with async_session() as session:
        latest = await get_latest_timestamp(session, symbol, timeframe)
    if latest:
        # Start from the next candle after the latest one
        since_ms = int(latest.timestamp() * 1000) + tf_ms
        log.info(
            "incremental_backfill",
            symbol=symbol,
            timeframe=timeframe,
            since=latest.isoformat(),
        )
    else:
        since_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
        log.info(
            "full_backfill",
            symbol=symbol,
            timeframe=timeframe,
            days=days,
        )

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    total_saved = 0

    while since_ms < now_ms:
        candles = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                candles = await client.fetch_ohlcv(
                    ccxt_symbol, timeframe=timeframe, since=since_ms, limit=BATCH_SIZE
                )
                break
            except Exception:
                log.exception(
                    "fetch_ohlcv_error",
                    symbol=symbol,
                    timeframe=timeframe,
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        if candles is None:
            log.error("fetch_ohlcv_failed_all_retries", symbol=symbol, timeframe=timeframe)
            break

        if not candles:
            break

        async with async_session() as session:
            saved = await save_candles(session, symbol, timeframe, candles)
        total_saved += saved

        # Move to after the last candle
        last_ts = candles[-1][0]
        since_ms = last_ts + tf_ms

        # If we got fewer than BATCH_SIZE, we've reached the end
        if len(candles) < BATCH_SIZE:
            break

        await asyncio.sleep(REQUEST_DELAY)

    log.info(
        "backfill_complete",
        symbol=symbol,
        timeframe=timeframe,
        candles_saved=total_saved,
    )
    return total_saved


async def backfill_all(
    client: ExchangeClient,
    symbols: list[str],
    timeframes: list[str] | None = None,
    days: int = 90,
) -> dict[str, int]:
    """Backfill OHLCV for multiple symbols and timeframes.

    Returns dict of {symbol: total_candles_saved}.
    """
    if timeframes is None:
        timeframes = TIMEFRAMES

    results: dict[str, int] = {}
    total_pairs = len(symbols) * len(timeframes)
    completed = 0

    for symbol in symbols:
        symbol_total = 0
        for tf in timeframes:
            count = await backfill_symbol(client, symbol, tf, days=days)
            symbol_total += count
            completed += 1
            if completed % 10 == 0:
                log.info("backfill_progress", completed=completed, total=total_pairs)
        results[symbol] = symbol_total

    log.info("backfill_all_complete", symbols=len(symbols), total_candles=sum(results.values()))
    return results


def _to_ccxt_symbol(db_symbol: str) -> str:
    """Convert DB symbol (BTCUSDT) to ccxt format (BTC/USDT).

    Handles common quote currencies: USDT, USDC, BTC, ETH.
    """
    for quote in ("USDT", "USDC", "BTC", "ETH"):
        if db_symbol.endswith(quote):
            base = db_symbol[: -len(quote)]
            return f"{base}/{quote}"
    return db_symbol
