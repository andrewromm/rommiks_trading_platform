"""CLI commands for Telegram delivery."""

import asyncio

import typer

from src.core.logger import get_logger, setup_logging

log = get_logger("delivery.cli")

app = typer.Typer(help="Telegram delivery commands")


@app.command()
def bot() -> None:
    """Start the Telegram bot (polling mode)."""
    setup_logging("INFO")
    asyncio.run(_run_bot())


async def _run_bot() -> None:
    from src.delivery.bot import run_bot

    await run_bot()


@app.command()
def notify(
    symbol: str = typer.Option("BTCUSDT", help="Symbol"),
    direction: str = typer.Option("long", help="Direction (long/short)"),
) -> None:
    """Send a test notification to Telegram."""
    setup_logging("INFO")
    asyncio.run(_notify(symbol, direction))


async def _notify(symbol: str, direction: str) -> None:
    from src.delivery.notifier import send_message

    text = f"Test notification: {direction.upper()} {symbol}"
    success = await send_message(text)
    if success:
        typer.echo("Notification sent successfully")
    else:
        typer.echo("Failed to send notification", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
