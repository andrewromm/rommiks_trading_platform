"""Telegram notification sender — push signals and alerts to chat."""

from __future__ import annotations

from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from src.core.config import settings
from src.core.logger import get_logger
from src.delivery.formatter import (
    format_new_listing,
    format_screener_top,
    format_signal,
)

log = get_logger("delivery.notifier")

# Cached Bot instance (singleton)
_bot: Bot | None = None

# Telegram API timeouts in seconds
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 15.0

# Minimum confidence threshold for signal notifications
_min_confidence: float = 0.55


def get_min_confidence() -> float:
    """Get current minimum confidence threshold."""
    return _min_confidence


def set_min_confidence(value: float) -> None:
    """Set minimum confidence threshold (0.0-1.0)."""
    global _min_confidence  # noqa: PLW0603
    _min_confidence = max(0.0, min(value, 1.0))


def _get_bot() -> Bot:
    """Get or create a cached Telegram Bot instance."""
    global _bot  # noqa: PLW0603
    if _bot is None:
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        request = HTTPXRequest(
            connect_timeout=_CONNECT_TIMEOUT,
            read_timeout=_READ_TIMEOUT,
        )
        _bot = Bot(token=settings.telegram_bot_token, request=request)
    return _bot


def _get_chat_id() -> str:
    """Get target chat ID."""
    if not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is not configured")
    return settings.telegram_chat_id


async def send_message(text: str) -> bool:
    """Send a plain text message to the configured Telegram chat.

    Returns True on success, False on failure.
    """
    try:
        bot = _get_bot()
        chat_id = _get_chat_id()
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except TelegramError as e:
        log.error("telegram_send_failed", error=str(e))
        return False


async def notify_signal(signal_dict: dict) -> bool:
    """Format and send a trading signal notification.

    Skips signals below the configured min_confidence threshold.
    """
    confidence = signal_dict.get("confidence", 0)
    if confidence < _min_confidence:
        log.debug(
            "signal_below_min_confidence",
            symbol=signal_dict.get("symbol"),
            confidence=confidence,
            min_confidence=_min_confidence,
        )
        return False

    text = format_signal(signal_dict)
    log.info(
        "sending_signal_notification",
        symbol=signal_dict.get("symbol"),
        direction=signal_dict.get("direction"),
        confidence=confidence,
    )
    return await send_message(text)


async def notify_screener(ranked: list[dict], title: str = "Daily Screener") -> bool:
    """Format and send screener top-N."""
    text = format_screener_top(ranked, title)
    log.info("sending_screener_notification", count=len(ranked))
    return await send_message(text)


async def notify_new_listing(symbol: str, base: str, quote: str) -> bool:
    """Send new listing alert."""
    text = format_new_listing(symbol, base, quote)
    log.info("sending_listing_notification", symbol=symbol)
    return await send_message(text)
