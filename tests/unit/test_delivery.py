"""Unit tests for the delivery module (formatter, notifier)."""

from decimal import Decimal

from src.delivery.formatter import (
    _fmt_price,
    _fmt_volume,
    format_new_listing,
    format_portfolio,
    format_screener_top,
    format_signal,
    format_status,
    format_trade_closed,
    format_trade_opened,
)


class TestFormatter:
    def test_fmt_price_large(self):
        assert _fmt_price(Decimal("70735.20")) == "70,735.20"

    def test_fmt_price_medium(self):
        assert _fmt_price(Decimal("2.5432")) == "2.5432"

    def test_fmt_price_small(self):
        assert _fmt_price(Decimal("0.00012345")) == "0.00012345"

    def test_fmt_price_none(self):
        assert _fmt_price(None) == "\u2014"

    def test_fmt_volume(self):
        assert _fmt_volume(1_500_000_000) == "$1.5B"
        assert _fmt_volume(2_500_000) == "$2.5M"
        assert _fmt_volume(50_000) == "$50K"
        assert _fmt_volume(500) == "$500"

    def test_format_signal_long(self):
        signal = {
            "symbol": "BTCUSDT",
            "direction": "long",
            "timeframe": "1h",
            "confidence": 0.75,
            "entry_price": Decimal("70000"),
            "stop_loss": Decimal("69000"),
            "take_profit_1": Decimal("71500"),
            "take_profit_2": Decimal("72500"),
            "take_profit_3": None,
            "risk_reward": 1.5,
            "position_size_pct": 10.0,
            "indicators": {"reasons": ["ema_21 > ema_50", "macd_bullish"]},
        }
        text = format_signal(signal)
        assert "LONG" in text
        assert "BTCUSDT" in text
        assert "70,000.00" in text
        assert "75%" in text
        assert "macd_bullish" in text

    def test_format_signal_short(self):
        signal = {
            "symbol": "ETHUSDT",
            "direction": "short",
            "timeframe": "4h",
            "confidence": 0.6,
            "entry_price": Decimal("2100"),
            "stop_loss": Decimal("2200"),
            "take_profit_1": Decimal("1950"),
            "take_profit_2": None,
            "take_profit_3": None,
            "risk_reward": 1.5,
            "position_size_pct": None,
            "indicators": {},
        }
        text = format_signal(signal)
        assert "SHORT" in text
        assert "ETHUSDT" in text

    def test_format_screener_top(self):
        ranked = [
            {"symbol": "BTCUSDT", "score": 85, "trend": "bullish", "volume_24h_usd": 5e9},
            {"symbol": "ETHUSDT", "score": 72, "trend": "neutral", "volume_24h_usd": 2e9},
        ]
        text = format_screener_top(ranked)
        assert "BTCUSDT" in text
        assert "ETHUSDT" in text
        assert "1." in text
        assert "2." in text

    def test_format_portfolio_empty(self):
        text = format_portfolio([])
        assert "no open trades" in text

    def test_format_portfolio_with_trades(self):
        trades = [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "direction": "long",
                "entry_price": Decimal("70000"),
                "size_usdt": Decimal("100"),
                "unrealized_pnl": 5.50,
            }
        ]
        text = format_portfolio(trades)
        assert "BTCUSDT" in text
        assert "+5.50" in text

    def test_format_trade_opened(self):
        text = format_trade_opened({
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": Decimal("70000"),
            "size_usdt": Decimal("100"),
        })
        assert "LONG" in text
        assert "BTCUSDT" in text

    def test_format_trade_closed(self):
        text = format_trade_closed({
            "symbol": "BTCUSDT",
            "direction": "long",
            "exit_price": Decimal("71000"),
            "pnl": Decimal("1.43"),
            "pnl_pct": 1.43,
        })
        assert "+1.43" in text

    def test_format_new_listing(self):
        text = format_new_listing("NEWUSDT", "NEW", "USDT")
        assert "NEWUSDT" in text
        assert "NEW/USDT" in text

    def test_format_status(self):
        text = format_status({
            "symbols_count": 50,
            "candles_count": 10000,
            "signals_24h": 5,
            "last_signal_time": "2026-02-15 12:00 UTC",
            "uptime": "2h 30m",
        })
        assert "50" in text
        assert "10000" in text
        assert "2h 30m" in text
