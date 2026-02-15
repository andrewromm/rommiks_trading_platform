"""OHLCV storage layer — batch upsert and queries."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import get_logger
from src.core.models import OHLCV

log = get_logger("collector.storage")


async def save_candles(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    candles: list[list],
) -> int:
    """Batch upsert OHLCV candles. Returns number of rows affected.

    candles: list of [timestamp_ms, open, high, low, close, volume] from ccxt.
    """
    if not candles:
        return 0

    values = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.fromtimestamp(c[0] / 1000, tz=datetime.UTC),
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5],
        }
        for c in candles
        if c[1] is not None  # skip incomplete candles
    ]

    if not values:
        return 0

    stmt = pg_insert(OHLCV).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_ohlcv_symbol_tf_ts",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def get_latest_timestamp(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
) -> datetime | None:
    """Get the latest candle timestamp for a symbol/timeframe pair."""
    result = await session.execute(
        select(OHLCV.timestamp)
        .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_candle_count(
    session: AsyncSession,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> int:
    """Count candles, optionally filtered by symbol and/or timeframe."""
    from sqlalchemy import func

    query = select(func.count(OHLCV.id))
    if symbol:
        query = query.where(OHLCV.symbol == symbol)
    if timeframe:
        query = query.where(OHLCV.timeframe == timeframe)
    result = await session.execute(query)
    return result.scalar_one()
