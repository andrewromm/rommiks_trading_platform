"""CLI commands for screener and scheduler."""

import asyncio

import typer

from src.core.logger import get_logger, setup_logging
from src.delivery.formatter import _fmt_volume

log = get_logger("screener.cli")

app = typer.Typer(help="Screener and scheduler commands")


@app.command()
def scan(
    top: int = typer.Option(10, help="Number of top coins to show"),
    timeframe: str = typer.Option("1h", help="Timeframe for analysis"),
) -> None:
    """Run coin screener and show top results."""
    setup_logging("INFO")
    asyncio.run(_scan(top, timeframe))


async def _scan(top: int, timeframe: str) -> None:
    from src.screener.screener import run_screener

    log.info("screener_starting", top=top, timeframe=timeframe)
    results = await run_screener(timeframe=timeframe, top_n=top, min_volume_usd=0)

    if not results:
        typer.echo("No coins qualified for screening.")
        return

    header = (
        f"{'#':>3} {'Symbol':<12} {'Score':>6} {'Trend':<8} "
        f"{'RSI':>5} {'Vol 24h':>10}"
    )
    typer.echo(f"\n{header}")
    typer.echo("-" * 52)
    for i, r in enumerate(results, 1):
        rsi_str = f"{r['rsi']:.0f}" if r.get("rsi") is not None else "—"
        vol_str = _fmt_volume(r.get("volume_24h_usd", 0))
        typer.echo(
            f"{i:>3} {r['symbol']:<12} {r['score']:>6.1f} {r['trend']:<8} "
            f"{rsi_str:>5} {vol_str:>10}"
        )

    typer.echo(f"\nTotal qualified: {len(results)}")


@app.command()
def listings() -> None:
    """Check for new ByBit spot listings."""
    setup_logging("INFO")
    asyncio.run(_listings())


async def _listings() -> None:
    from src.screener.listings import check_new_listings

    new_pairs = await check_new_listings()
    if new_pairs:
        typer.echo(f"New listings found: {len(new_pairs)}")
        for p in new_pairs:
            typer.echo(f"  {p['symbol']} ({p['base']}/{p['quote']})")
    else:
        typer.echo("No new listings.")


@app.command()
def scheduler(
    top: int = typer.Option(50, help="Number of symbols to track"),
) -> None:
    """Start the scheduler (runs analysis, screener, listing checks)."""
    setup_logging("INFO")
    asyncio.run(_scheduler(top))


async def _scheduler(top: int) -> None:
    from src.screener.scheduler import run_scheduler

    await run_scheduler(top=top)


if __name__ == "__main__":
    app()
