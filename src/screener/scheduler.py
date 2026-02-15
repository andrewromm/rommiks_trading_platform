"""Async scheduler — periodic analysis, screener, and listing checks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from src.core.logger import get_logger

log = get_logger("scheduler")

# Schedule intervals in seconds
INTERVAL_15M = 15 * 60       # 15 minutes
INTERVAL_1H = 60 * 60        # 1 hour
INTERVAL_4H = 4 * 60 * 60    # 4 hours
INTERVAL_DAILY = 24 * 60 * 60  # 24 hours
INTERVAL_LISTINGS = 15 * 60  # 15 minutes


async def _run_analysis(top: int, timeframe: str) -> None:
    """Run technical analysis for active symbols and timeframe."""
    from src.analyzer.engine import analyze_all
    from src.delivery.notifier import notify_signal

    symbols = await _get_symbols()
    symbols = symbols[:top]

    log.info("scheduled_analysis_start", timeframe=timeframe, symbols=len(symbols))

    signals = await analyze_all(symbols, [timeframe])

    for signal in signals:
        await notify_signal(signal.to_dict())

    log.info(
        "scheduled_analysis_complete",
        timeframe=timeframe,
        signals_generated=len(signals),
    )


async def _run_screener() -> None:
    """Run daily screener and send digest."""
    from src.delivery.notifier import notify_screener
    from src.screener.screener import run_screener

    log.info("scheduled_screener_start")
    results = await run_screener(timeframe="1h", top_n=10)

    if results:
        await notify_screener(results, title="Daily Screener Top 10")

    log.info("scheduled_screener_complete", results=len(results))


async def _run_listing_check() -> None:
    """Check for new listings and send alerts."""
    from src.delivery.notifier import notify_new_listing
    from src.screener.listings import check_new_listings

    new = await check_new_listings()
    for pair in new:
        await notify_new_listing(pair["symbol"], pair["base"], pair["quote"])


async def _get_symbols() -> list[str]:
    """Get active symbols for analysis."""
    from src.collector.symbols import get_active_symbols
    from src.core.database import async_session

    async with async_session() as session:
        return await get_active_symbols(session)


async def _loop(name: str, interval: int, func, *args) -> None:
    """Generic loop that runs func every interval seconds."""
    while True:
        try:
            start = datetime.now(UTC)
            await func(*args)
            elapsed = (datetime.now(UTC) - start).total_seconds()
            log.debug("task_completed", task=name, elapsed=f"{elapsed:.1f}s")
        except Exception:
            log.exception("task_error", task=name)

        await asyncio.sleep(interval)


async def run_scheduler(
    top: int = 50,
    enable_15m: bool = True,
    enable_1h: bool = True,
    enable_4h: bool = True,
    enable_screener: bool = True,
    enable_listings: bool = True,
) -> None:
    """Start all scheduled tasks as concurrent asyncio tasks.

    Runs indefinitely until cancelled. Symbols are refreshed on each
    analysis cycle, so newly added symbols are picked up automatically.
    """
    # Verify there are symbols before starting
    symbols = await _get_symbols()
    if not symbols:
        log.warning("scheduler_no_symbols", msg="Run collector backfill first")
        return

    log.info("scheduler_starting", symbols=len(symbols[:top]))

    tasks: list[asyncio.Task] = []

    if enable_15m:
        tasks.append(asyncio.create_task(
            _loop("analyze_15m", INTERVAL_15M, _run_analysis, top, "15m")
        ))
    if enable_1h:
        tasks.append(asyncio.create_task(
            _loop("analyze_1h", INTERVAL_1H, _run_analysis, top, "1h")
        ))
    if enable_4h:
        tasks.append(asyncio.create_task(
            _loop("analyze_4h", INTERVAL_4H, _run_analysis, top, "4h")
        ))
    if enable_screener:
        tasks.append(asyncio.create_task(
            _loop("screener", INTERVAL_DAILY, _run_screener)
        ))
    if enable_listings:
        tasks.append(asyncio.create_task(
            _loop("listings", INTERVAL_LISTINGS, _run_listing_check)
        ))

    log.info("scheduler_running", tasks=len(tasks))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("scheduler_stopped")
        for t in tasks:
            t.cancel()
