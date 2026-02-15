"""Unit tests for the screener module."""

import numpy as np
import pandas as pd

from src.screener.screener import (
    MIN_CANDLES_SCREEN,
    WEIGHT_RSI_SETUP,
    WEIGHT_TREND,
    WEIGHT_VOLATILITY,
    WEIGHT_VOLUME,
    compute_score,
)


def _make_ohlcv_df(n: int = 100, trend: str = "up") -> pd.DataFrame:
    """Create synthetic OHLCV for screener tests."""
    np.random.seed(42)
    base = 100.0

    if trend == "up":
        closes = base + np.cumsum(np.random.normal(0.2, 1.0, n))
    elif trend == "down":
        closes = base + np.cumsum(np.random.normal(-0.2, 1.0, n))
    else:
        closes = base + np.cumsum(np.random.normal(0.0, 1.0, n))

    closes = np.maximum(closes, 10.0)
    highs = closes + np.abs(np.random.normal(1.0, 0.5, n))
    lows = closes - np.abs(np.random.normal(1.0, 0.5, n))
    opens = closes + np.random.normal(0.0, 0.5, n)
    volumes = np.abs(np.random.normal(1000, 200, n))

    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h"),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


class TestScreener:
    def test_compute_score_returns_dict(self):
        df = _make_ohlcv_df(100)
        result = compute_score(df)
        assert isinstance(result, dict)
        assert "score" in result
        assert "trend" in result
        assert not result.get("skip")

    def test_compute_score_range(self):
        df = _make_ohlcv_df(100)
        result = compute_score(df)
        assert 0 <= result["score"] <= 100

    def test_compute_score_insufficient_data(self):
        df = _make_ohlcv_df(10)
        result = compute_score(df)
        assert result["skip"] is True
        assert result["score"] == 0

    def test_compute_score_uptrend(self):
        df = _make_ohlcv_df(250, trend="up")
        result = compute_score(df)
        assert result["trend"] in ("bullish", "neutral", "bearish")
        assert result["score"] > 0

    def test_compute_score_downtrend(self):
        df = _make_ohlcv_df(250, trend="down")
        result = compute_score(df)
        assert result["trend"] in ("bullish", "neutral", "bearish")

    def test_compute_score_has_subscores(self):
        df = _make_ohlcv_df(100)
        result = compute_score(df)
        assert "trend_score" in result
        assert "volume_score" in result
        assert "volatility_score" in result
        assert "rsi_score" in result

    def test_weights_sum_to_100(self):
        total = WEIGHT_TREND + WEIGHT_VOLUME + WEIGHT_VOLATILITY + WEIGHT_RSI_SETUP
        assert total == 100

    def test_min_candles_screen(self):
        assert MIN_CANDLES_SCREEN >= 20
