"""Telegram message formatting for signals, screener, and portfolio."""

from __future__ import annotations

from decimal import Decimal


def format_signal(signal: dict) -> str:
    """Format a trading signal for Telegram (MarkdownV2-safe plain text).

    Accepts a dict with keys matching Signal model fields.
    """
    direction = signal["direction"].upper()
    symbol = signal["symbol"]
    emoji = "\U0001f7e2" if direction == "LONG" else "\U0001f534"  # green/red circle

    conf = signal["confidence"]
    conf_str = f"{conf:.0%}" if isinstance(conf, float) else str(conf)

    entry = _fmt_price(signal["entry_price"])
    sl = _fmt_price(signal["stop_loss"])
    tp1 = _fmt_price(signal["take_profit_1"])
    tp2 = _fmt_price(signal.get("take_profit_2"))
    tp3 = _fmt_price(signal.get("take_profit_3"))
    rr = signal.get("risk_reward", "—")
    tf = signal.get("timeframe", "")
    pos_size = signal.get("position_size_pct")

    reasons = signal.get("indicators", {}).get("reasons", [])
    reasons_str = ", ".join(reasons) if reasons else "—"

    lines = [
        f"{emoji} {direction} {symbol} ({tf})",
        "",
        f"Entry:      {entry}",
        f"Stop Loss:  {sl}",
        f"TP1:        {tp1}",
    ]
    if tp2:
        lines.append(f"TP2:        {tp2}")
    if tp3:
        lines.append(f"TP3:        {tp3}")

    lines.extend([
        "",
        f"Confidence: {conf_str}",
        f"R:R:        {rr}",
    ])
    if pos_size is not None:
        lines.append(f"Position:   {pos_size}% of capital")

    lines.extend([
        "",
        f"Reasons: {reasons_str}",
    ])

    return "\n".join(lines)


def format_screener_top(ranked: list[dict], title: str = "Daily Screener") -> str:
    """Format screener top-N list for Telegram."""
    lines = [f"\U0001f4ca {title}", ""]

    for i, item in enumerate(ranked, 1):
        symbol = item["symbol"]
        score = item.get("score", 0)
        trend = item.get("trend", "—")
        vol_24h = item.get("volume_24h_usd")
        vol_str = _fmt_volume(vol_24h) if vol_24h else "—"

        trend_emoji = "\U00002b06" if trend == "bullish" else (
            "\U00002b07" if trend == "bearish" else "\U00002796"
        )  # up/down/minus

        lines.append(f"{i}. {symbol}  {trend_emoji}  score={score:.0f}  vol={vol_str}")

    return "\n".join(lines)


def format_portfolio(trades: list[dict]) -> str:
    """Format open paper trades for Telegram."""
    if not trades:
        return "\U0001f4bc Portfolio: no open trades"

    lines = ["\U0001f4bc Open Trades", ""]
    total_pnl = 0.0

    for t in trades:
        symbol = t["symbol"]
        direction = t["direction"].upper()
        entry = _fmt_price(t["entry_price"])
        size = t.get("size_usdt", "—")
        pnl = t.get("unrealized_pnl")
        pnl_str = f"{pnl:+.2f} USDT" if pnl is not None else "—"
        if pnl is not None:
            total_pnl += float(pnl)

        lines.append(
            f"#{t.get('id', '?')} {direction} {symbol} "
            f"@ {entry} ({size} USDT) P&L: {pnl_str}"
        )

    lines.extend(["", f"Total unrealized P&L: {total_pnl:+.2f} USDT"])
    return "\n".join(lines)


def format_trade_opened(trade: dict) -> str:
    """Format trade opened confirmation."""
    return (
        f"\U00002705 Trade opened: {trade['direction'].upper()} {trade['symbol']} "
        f"@ {_fmt_price(trade['entry_price'])} ({trade['size_usdt']} USDT)"
    )


def format_trade_closed(trade: dict) -> str:
    """Format trade closed confirmation with P&L."""
    pnl = trade.get("pnl", 0)
    pnl_pct = trade.get("pnl_pct", 0)
    emoji = "\U0001f4b0" if float(pnl) >= 0 else "\U0001f4a8"  # money bag / dash
    return (
        f"{emoji} Trade closed: {trade['direction'].upper()} {trade['symbol']} "
        f"@ {_fmt_price(trade.get('exit_price'))} | "
        f"P&L: {float(pnl):+.2f} USDT ({float(pnl_pct):+.1f}%)"
    )


def format_new_listing(symbol: str, base: str, quote: str) -> str:
    """Format new listing alert."""
    return f"\U0001f195 New listing: {symbol} ({base}/{quote})"


def format_status(data: dict) -> str:
    """Format system status message."""
    lines = [
        "\U00002699 System Status",
        "",
        f"Symbols tracked: {data.get('symbols_count', '—')}",
        f"OHLCV candles:   {data.get('candles_count', '—')}",
        f"Signals (24h):   {data.get('signals_24h', '—')}",
        f"Last signal:     {data.get('last_signal_time', '—')}",
        f"Uptime:          {data.get('uptime', '—')}",
    ]
    return "\n".join(lines)


# --- Helpers ---

def _fmt_price(value: Decimal | float | str | None) -> str:
    """Format a price value for display."""
    if value is None:
        return "—"
    v = float(value)
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:.4f}"
    return f"{v:.8f}"


def _fmt_volume(usd: float) -> str:
    """Format volume in human-readable form."""
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.1f}B"
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.1f}M"
    if usd >= 1_000:
        return f"${usd / 1_000:.0f}K"
    return f"${usd:.0f}"
