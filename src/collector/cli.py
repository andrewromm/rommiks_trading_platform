"""CLI commands for the market data collector."""

import asyncio

import typer

from src.core.logger import get_logger, setup_logging

log = get_logger("collector.cli")

app = typer.Typer(help="Market data collector commands")


@app.command()
def backfill(
    symbol: str = typer.Option("", help="Single symbol (e.g. BTCUSDT). Empty = all active."),
    timeframe: str = typer.Option("", help="Single timeframe (e.g. 1h). Empty = all."),
    days: int = typer.Option(90, help="How many days of history to load"),
    top: int = typer.Option(50, help="Fetch top N symbols by volume (if no symbol specified)"),
) -> None:
    """Backfill historical OHLCV data from ByBit."""
    setup_logging("INFO")
    asyncio.run(_backfill(symbol, timeframe, days, top))


async def _backfill(symbol: str, timeframe: str, days: int, top: int) -> None:
    from src.collector.exchange import ExchangeClient
    from src.collector.ohlcv import TIMEFRAMES, backfill_all
    from src.collector.symbols import (
        fetch_usdt_spot_pairs,
        get_top_symbols_by_volume,
        sync_symbols_to_db,
    )
    from src.core.database import async_session

    async with ExchangeClient() as client:
        if symbol:
            # Single symbol mode
            symbols = [symbol]
            timeframes = [timeframe] if timeframe else TIMEFRAMES
        else:
            # Discover and sync symbols
            pairs = await fetch_usdt_spot_pairs(client)
            top_pairs = await get_top_symbols_by_volume(client, pairs, top_n=top)

            async with async_session() as session:
                await sync_symbols_to_db(session, top_pairs)

            symbols = [p["symbol"].replace("/", "") for p in top_pairs]
            timeframes = [timeframe] if timeframe else TIMEFRAMES

        log.info(
            "backfill_starting",
            symbols=len(symbols),
            timeframes=timeframes,
            days=days,
        )

        results = await backfill_all(client, symbols, timeframes, days)
        total = sum(results.values())
        log.info("backfill_finished", symbols=len(results), total_candles=total)


@app.command()
def stream(
    top: int = typer.Option(50, help="Number of top symbols to stream"),
) -> None:
    """Stream real-time ticker data via WebSocket."""
    setup_logging("INFO")
    asyncio.run(_stream(top))


async def _stream(top: int) -> None:
    import signal

    from src.collector.exchange import ExchangeClient
    from src.collector.symbols import (
        fetch_usdt_spot_pairs,
        get_top_symbols_by_volume,
    )
    from src.collector.websocket import WebSocketManager
    from src.core.config import settings
    from src.core.redis import close_redis, get_redis

    # Get top symbols
    async with ExchangeClient() as client:
        pairs = await fetch_usdt_spot_pairs(client)
        top_pairs = await get_top_symbols_by_volume(client, pairs, top_n=top)

    symbols = [p["symbol"].replace("/", "") for p in top_pairs]
    log.info("stream_starting", symbols=len(symbols))

    redis_client = await get_redis()
    shutdown_event = asyncio.Event()

    ws = WebSocketManager(
        symbols=symbols,
        redis_client=redis_client,
        testnet=settings.bybit_testnet,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (ws.stop(), shutdown_event.set()))

    try:
        await ws.start(shutdown_event)
    finally:
        await close_redis()


@app.command()
def status() -> None:
    """Show collector data status — candle counts per symbol/timeframe."""
    setup_logging("INFO")
    asyncio.run(_status())


async def _status() -> None:
    from sqlalchemy import func, select

    from src.core.database import async_session
    from src.core.models import OHLCV

    async with async_session() as session:
        # Candle counts by symbol and timeframe
        result = await session.execute(
            select(
                OHLCV.symbol,
                OHLCV.timeframe,
                func.count().label("count"),
                func.min(OHLCV.timestamp).label("first"),
                func.max(OHLCV.timestamp).label("last"),
            )
            .group_by(OHLCV.symbol, OHLCV.timeframe)
            .order_by(OHLCV.symbol, OHLCV.timeframe)
        )
        rows = result.all()

    if not rows:
        typer.echo("No OHLCV data in database.")
        return

    typer.echo(f"{'Symbol':<12} {'TF':<6} {'Count':>8}  {'First':>20}  {'Last':>20}")
    typer.echo("-" * 72)
    for row in rows:
        typer.echo(
            f"{row.symbol:<12} {row.timeframe:<6} {row.count:>8}  "
            f"{row.first.strftime('%Y-%m-%d %H:%M'):>20}  "
            f"{row.last.strftime('%Y-%m-%d %H:%M'):>20}"
        )

    total = sum(r.count for r in rows)
    typer.echo(f"\nTotal candles: {total:,}")


if __name__ == "__main__":
    app()
