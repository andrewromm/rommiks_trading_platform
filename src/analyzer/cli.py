"""CLI commands for the technical analysis engine."""

import asyncio

import typer

from src.core.logger import get_logger, setup_logging

log = get_logger("analyzer.cli")

app = typer.Typer(help="Technical analysis engine commands")


@app.command()
def analyze(
    symbol: str = typer.Option("BTCUSDT", help="Symbol to analyze (e.g. BTCUSDT)"),
    timeframe: str = typer.Option("1h", help="Timeframe (15m, 1h, 4h)"),
) -> None:
    """Analyze a single symbol/timeframe and generate signals."""
    setup_logging("INFO")
    asyncio.run(_analyze(symbol, timeframe))


async def _analyze(symbol: str, timeframe: str) -> None:
    from src.analyzer.engine import analyze_symbol

    log.info("analyze_starting", symbol=symbol, timeframe=timeframe)
    signals = await analyze_symbol(symbol, timeframe)
    if signals:
        for s in signals:
            typer.echo(
                f"SIGNAL: {s.direction.value.upper()} {s.symbol} @ {s.entry_price} "
                f"| SL={s.stop_loss} TP1={s.take_profit_1} "
                f"| confidence={s.confidence:.0%} R:R={s.risk_reward}"
            )
    else:
        typer.echo(f"No signal for {symbol}/{timeframe}")


@app.command()
def scan(
    top: int = typer.Option(50, help="Number of top symbols to scan"),
    timeframe: str = typer.Option("", help="Single timeframe. Empty = all entry TFs (15m,1h,4h)"),
) -> None:
    """Scan multiple symbols for trading signals."""
    setup_logging("INFO")
    asyncio.run(_scan(top, timeframe))


async def _scan(top: int, timeframe: str) -> None:
    from src.analyzer.engine import ENTRY_TIMEFRAMES, analyze_all
    from src.collector.symbols import get_active_symbols
    from src.core.database import async_session

    async with async_session() as session:
        symbols = await get_active_symbols(session)

    if not symbols:
        typer.echo("No active symbols in database. Run collector backfill first.")
        return

    symbols = symbols[:top]
    timeframes = [timeframe] if timeframe else ENTRY_TIMEFRAMES

    log.info("scan_starting", symbols=len(symbols), timeframes=timeframes)
    signals = await analyze_all(symbols, timeframes)

    header = (
        f"{'Symbol':<12} {'Dir':<6} {'TF':<5} {'Conf':>5}  "
        f"{'Entry':>12}  {'SL':>12}  {'TP1':>12}"
    )
    typer.echo(f"\n{header}")
    typer.echo("-" * 72)
    for s in signals:
        typer.echo(
            f"{s.symbol:<12} {s.direction.value.upper():<6} {s.timeframe:<5} "
            f"{s.confidence:>4.0%}  {s.entry_price:>12}  {s.stop_loss:>12}  {s.take_profit_1:>12}"
        )

    typer.echo(f"\nTotal signals: {len(signals)}")


@app.command()
def signals(
    symbol: str = typer.Option("", help="Filter by symbol"),
    limit: int = typer.Option(20, help="Number of recent signals to show"),
) -> None:
    """Show recent signals from the database."""
    setup_logging("INFO")
    asyncio.run(_signals(symbol, limit))


async def _signals(symbol: str, limit: int) -> None:
    from sqlalchemy import select

    from src.core.database import async_session
    from src.core.models import Signal

    async with async_session() as session:
        query = select(Signal)
        if symbol:
            query = query.where(Signal.symbol == symbol)
        query = query.order_by(Signal.created_at.desc()).limit(limit)
        result = await session.execute(query)
        rows = result.scalars().all()

    if not rows:
        typer.echo("No signals found.")
        return

    typer.echo(
        f"{'ID':>5} {'Symbol':<12} {'Dir':<6} {'TF':<5} {'Conf':>5}  "
        f"{'Entry':>12}  {'Status':<10} {'Created':<20}"
    )
    typer.echo("-" * 85)
    for s in rows:
        typer.echo(
            f"{s.id:>5} {s.symbol:<12} {s.direction.value.upper():<6} {s.timeframe:<5} "
            f"{s.confidence:>4.0%}  {s.entry_price:>12}  {s.status.value:<10} "
            f"{s.created_at.strftime('%Y-%m-%d %H:%M'):<20}"
        )


if __name__ == "__main__":
    app()
