"""Telegram bot — interactive commands for signals, screener, paper trading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from src.core.config import settings
from src.core.database import async_session
from src.core.logger import get_logger
from src.core.models import OHLCV, PaperTrade, Signal, SignalDirection, Symbol
from src.delivery.formatter import (
    format_portfolio,
    format_signal,
    format_status,
    format_trade_closed,
    format_trade_opened,
)
from src.delivery.notifier import get_min_confidence, set_min_confidence

log = get_logger("delivery.bot")

# Bot start time for uptime tracking
_start_time: datetime | None = None



async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.effective_message.reply_text(
        "Trading Bot active.\n\n"
        "Commands:\n"
        "/status — system status\n"
        "/top [N] — top N coins by screener score\n"
        "/signal SYMBOL — latest signal for a coin\n"
        "/trade SYMBOL long|short SIZE — open paper trade\n"
        "/close ID PRICE — close paper trade\n"
        "/portfolio — open paper trades\n"
        "/settings [min_confidence] — notification filter"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — system overview."""
    async with async_session() as session:
        symbols_count = await session.scalar(
            select(func.count()).select_from(Symbol).where(Symbol.is_active.is_(True))
        )
        candles_count = await session.scalar(
            select(func.count()).select_from(OHLCV)
        )
        cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
        signals_24h = await session.scalar(
            select(func.count()).select_from(Signal).where(Signal.created_at >= cutoff_24h)
        )
        last_signal = await session.scalar(
            select(Signal.created_at).order_by(Signal.created_at.desc()).limit(1)
        )

    uptime = "—"
    if _start_time:
        delta = datetime.now(UTC) - _start_time
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        uptime = f"{hours}h {minutes}m"

    last_str = last_signal.strftime("%Y-%m-%d %H:%M UTC") if last_signal else "—"

    text = format_status({
        "symbols_count": symbols_count or 0,
        "candles_count": candles_count or 0,
        "signals_24h": signals_24h or 0,
        "last_signal_time": last_str,
        "uptime": uptime,
    })
    await update.effective_message.reply_text(text)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /top [N] — show top coins from latest screener run."""
    n = 10
    if context.args:
        try:
            n = int(context.args[0])
            n = min(max(n, 1), 50)
        except ValueError:
            pass

    # Get latest signals grouped by symbol, ordered by confidence
    async with async_session() as session:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        result = await session.execute(
            select(Signal)
            .where(Signal.created_at >= cutoff, Signal.source == "technical_analysis")
            .order_by(Signal.confidence.desc())
            .limit(n)
        )
        signals = result.scalars().all()

    if not signals:
        await update.effective_message.reply_text("No signals in the last 24 hours.")
        return

    lines = [f"\U0001f3af Top {len(signals)} signals (24h)", ""]
    for i, s in enumerate(signals, 1):
        emoji = "\U0001f7e2" if s.direction == SignalDirection.LONG else "\U0001f534"
        lines.append(
            f"{i}. {emoji} {s.symbol} {s.direction.value.upper()} "
            f"({s.timeframe}) conf={s.confidence:.0%} R:R={s.risk_reward}"
        )

    await update.effective_message.reply_text("\n".join(lines))


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /signal SYMBOL — show latest signal for a symbol."""
    if not context.args:
        await update.effective_message.reply_text("Usage: /signal BTCUSDT")
        return

    symbol = context.args[0].upper()

    async with async_session() as session:
        result = await session.execute(
            select(Signal)
            .where(Signal.symbol == symbol)
            .order_by(Signal.created_at.desc())
            .limit(1)
        )
        signal = result.scalar_one_or_none()

    if not signal:
        await update.effective_message.reply_text(f"No signals found for {symbol}")
        return

    text = format_signal(signal.to_dict())
    age = datetime.now(UTC) - signal.created_at
    hours = int(age.total_seconds() // 3600)
    text += f"\n\nGenerated {hours}h ago | Status: {signal.status.value}"

    await update.effective_message.reply_text(text)


async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /trade SYMBOL long|short SIZE — open paper trade."""
    if not context.args or len(context.args) < 3:
        await update.effective_message.reply_text("Usage: /trade BTCUSDT long 100")
        return

    symbol = context.args[0].upper()
    direction_str = context.args[1].lower()
    size_str = context.args[2]

    if direction_str not in ("long", "short"):
        await update.effective_message.reply_text("Direction must be 'long' or 'short'")
        return

    try:
        size = Decimal(size_str)
        if size <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.effective_message.reply_text("Size must be a positive number (USDT)")
        return

    # Get current price and create trade in single session
    async with async_session() as session:
        result = await session.scalar(
            select(OHLCV.close)
            .where(OHLCV.symbol == symbol)
            .order_by(OHLCV.timestamp.desc())
            .limit(1)
        )

        if result is None:
            await update.effective_message.reply_text(
                f"No price data for {symbol}. Run backfill first."
            )
            return

        entry_price = Decimal(str(round(result, 8)))

        trade = PaperTrade(
            symbol=symbol,
            direction=SignalDirection(direction_str),
            entry_price=entry_price,
            size_usdt=size,
        )
        session.add(trade)
        await session.commit()
        await session.refresh(trade)

    text = format_trade_opened({
        "symbol": symbol,
        "direction": direction_str,
        "entry_price": entry_price,
        "size_usdt": size,
    })
    text += f"\nTrade ID: #{trade.id}"
    await update.effective_message.reply_text(text)


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /close ID PRICE — close paper trade."""
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text("Usage: /close 1 70000")
        return

    try:
        trade_id = int(context.args[0])
        exit_price = Decimal(context.args[1])
    except (ValueError, InvalidOperation):
        await update.effective_message.reply_text("Usage: /close <trade_id> <exit_price>")
        return

    async with async_session() as session:
        trade = await session.get(PaperTrade, trade_id)
        if not trade:
            await update.effective_message.reply_text(f"Trade #{trade_id} not found")
            return
        if trade.closed_at is not None:
            await update.effective_message.reply_text(f"Trade #{trade_id} is already closed")
            return

        trade.exit_price = exit_price
        trade.closed_at = datetime.now(UTC)

        # Calculate P&L
        entry = float(trade.entry_price)
        exit_f = float(exit_price)
        size_f = float(trade.size_usdt)

        if trade.direction == SignalDirection.LONG:
            pnl_pct = (exit_f - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_f) / entry * 100

        trade.pnl_pct = round(pnl_pct, 2)
        trade.pnl = Decimal(str(round(size_f * pnl_pct / 100, 8)))

        await session.commit()
        await session.refresh(trade)

    text = format_trade_closed({
        "symbol": trade.symbol,
        "direction": trade.direction.value,
        "exit_price": trade.exit_price,
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
    })
    await update.effective_message.reply_text(text)


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /portfolio — show open paper trades."""
    async with async_session() as session:
        result = await session.execute(
            select(PaperTrade)
            .where(PaperTrade.closed_at.is_(None))
            .order_by(PaperTrade.opened_at.desc())
        )
        trades = result.scalars().all()

        if not trades:
            text = format_portfolio([])
            await update.effective_message.reply_text(text)
            return

        # Load latest prices for all traded symbols in one query
        traded_symbols = list({t.symbol for t in trades})
        # Subquery: latest timestamp per symbol
        latest_ts = (
            select(OHLCV.symbol, func.max(OHLCV.timestamp).label("max_ts"))
            .where(OHLCV.symbol.in_(traded_symbols))
            .group_by(OHLCV.symbol)
            .subquery()
        )
        price_result = await session.execute(
            select(OHLCV.symbol, OHLCV.close)
            .join(
                latest_ts,
                (OHLCV.symbol == latest_ts.c.symbol)
                & (OHLCV.timestamp == latest_ts.c.max_ts),
            )
        )
        prices = {row[0]: float(row[1]) for row in price_result.all()}

    trade_dicts = []
    for t in trades:
        entry = float(t.entry_price)
        current = prices.get(t.symbol, entry)
        size_f = float(t.size_usdt)

        if t.direction == SignalDirection.LONG:
            pnl_pct = (current - entry) / entry * 100
        else:
            pnl_pct = (entry - current) / entry * 100

        unrealized = round(size_f * pnl_pct / 100, 2)

        trade_dicts.append({
            "id": t.id,
            "symbol": t.symbol,
            "direction": t.direction.value,
            "entry_price": t.entry_price,
            "size_usdt": t.size_usdt,
            "unrealized_pnl": unrealized,
        })

    text = format_portfolio(trade_dicts)
    await update.effective_message.reply_text(text)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings [min_confidence] — configure notification filter."""
    if context.args:
        try:
            val = float(context.args[0])
            if 0 <= val <= 1:
                set_min_confidence(val)
                await update.effective_message.reply_text(
                    f"Min confidence set to {get_min_confidence():.0%}"
                )
                return
            else:
                await update.effective_message.reply_text("Value must be between 0 and 1")
                return
        except ValueError:
            pass

    await update.effective_message.reply_text(
        f"Current min confidence: {get_min_confidence():.0%}\n"
        "Usage: /settings 0.7"
    )


def _build_chat_filter() -> filters.BaseFilter:
    """Build a filter that restricts commands to the configured chat ID."""
    if settings.telegram_chat_id:
        try:
            return filters.Chat(chat_id=int(settings.telegram_chat_id))
        except ValueError:
            log.warning("invalid_chat_id", chat_id=settings.telegram_chat_id)
    return filters.ALL


def create_app() -> Application:
    """Create and configure the Telegram bot application."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    app = Application.builder().token(settings.telegram_bot_token).build()

    chat_filter = _build_chat_filter()

    app.add_handler(CommandHandler("start", cmd_start, filters=chat_filter))
    app.add_handler(CommandHandler("help", cmd_start, filters=chat_filter))
    app.add_handler(CommandHandler("status", cmd_status, filters=chat_filter))
    app.add_handler(CommandHandler("top", cmd_top, filters=chat_filter))
    app.add_handler(CommandHandler("signal", cmd_signal, filters=chat_filter))
    app.add_handler(CommandHandler("trade", cmd_trade, filters=chat_filter))
    app.add_handler(CommandHandler("close", cmd_close, filters=chat_filter))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio, filters=chat_filter))
    app.add_handler(CommandHandler("settings", cmd_settings, filters=chat_filter))

    return app


async def run_bot() -> None:
    """Start the bot in polling mode."""
    import asyncio

    from telegram import BotCommand

    global _start_time  # noqa: PLW0603
    _start_time = datetime.now(UTC)

    log.info("telegram_bot_starting")
    app = create_app()
    await app.initialize()

    # Register commands in Telegram menu
    await app.bot.set_my_commands([
        BotCommand("status",    "System status & uptime"),
        BotCommand("top",       "Top N coins by signal confidence"),
        BotCommand("signal",    "Latest signal for a coin — /signal BTCUSDT"),
        BotCommand("trade",     "Open paper trade — /trade BTCUSDT long 100"),
        BotCommand("close",     "Close paper trade — /close ID PRICE"),
        BotCommand("portfolio", "Open paper trades with unrealized P&L"),
        BotCommand("settings",  "Set min confidence filter — /settings 0.7"),
        BotCommand("help",      "Show available commands"),
    ])
    log.info("telegram_commands_registered")

    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log.info("telegram_bot_running")

    # Keep running until stopped
    try:
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        log.info("telegram_bot_stopped")
