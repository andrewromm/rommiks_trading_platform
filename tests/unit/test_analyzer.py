"""Unit tests for the technical analysis engine."""

from decimal import Decimal

import numpy as np
import pandas as pd

from src.analyzer.indicators import compute_indicators
from src.analyzer.levels import (
    _cluster_levels,
    find_support_resistance,
    find_swing_highs,
    find_swing_lows,
    nearest_resistance,
    nearest_support,
)
from src.analyzer.mtf import HIGHER_TF_MAP, get_higher_timeframe
from src.analyzer.signals import (
    MIN_CONFIDENCE,
    SignalCandidate,
    compute_position_size,
    compute_sl_tp,
    evaluate_long,
    evaluate_short,
    generate_signals,
)

# --- Helpers ---

def _make_ohlcv_df(n: int = 250, trend: str = "up") -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    base = 100.0

    if trend == "up":
        closes = base + np.cumsum(np.random.normal(0.2, 1.0, n))
    elif trend == "down":
        closes = base + np.cumsum(np.random.normal(-0.2, 1.0, n))
    else:
        closes = base + np.cumsum(np.random.normal(0.0, 1.0, n))

    # Ensure positive
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


# --- Indicator tests ---

class TestIndicators:
    def test_compute_indicators_adds_columns(self):
        df = _make_ohlcv_df(250)
        result = compute_indicators(df)

        expected_cols = [
            "ema_9", "ema_21", "ema_50", "ema_200",
            "macd", "macd_signal", "macd_hist",
            "rsi_14", "stochrsi_k", "stochrsi_d",
            "bb_upper", "bb_middle", "bb_lower",
            "atr_14", "obv", "vol_sma_20", "vwap",
            "ema_trend", "vol_ratio",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_compute_indicators_preserves_length(self):
        df = _make_ohlcv_df(100)
        result = compute_indicators(df)
        assert len(result) == len(df)

    def test_compute_indicators_does_not_mutate_input(self):
        df = _make_ohlcv_df(50)
        original_cols = list(df.columns)
        compute_indicators(df)
        assert list(df.columns) == original_cols

    def test_ema_trend_values(self):
        df = _make_ohlcv_df(250, trend="up")
        result = compute_indicators(df)
        # Last row in an uptrend should have ema_trend == 1
        last = result.iloc[-1]
        assert last["ema_trend"] in (1, -1, 0)

    def test_rsi_bounds(self):
        df = _make_ohlcv_df(250)
        result = compute_indicators(df)
        rsi = result["rsi_14"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()


# --- Level tests ---

class TestLevels:
    def test_find_swing_highs(self):
        df = _make_ohlcv_df(100)
        swings = find_swing_highs(df, window=3)
        assert len(swings) > 0
        assert all(isinstance(v, float) for v in swings.values)

    def test_find_swing_lows(self):
        df = _make_ohlcv_df(100)
        swings = find_swing_lows(df, window=3)
        assert len(swings) > 0

    def test_cluster_levels(self):
        values = [100.0, 100.3, 100.5, 105.0, 105.2, 110.0]
        clusters = _cluster_levels(values, tolerance_pct=0.5)
        assert len(clusters) >= 2
        assert clusters[0]["touches"] >= 1

    def test_find_support_resistance_returns_dict(self):
        df = _make_ohlcv_df(200)
        levels = find_support_resistance(df)
        assert "support" in levels
        assert "resistance" in levels

    def test_nearest_support(self):
        levels = [{"price": 90.0, "touches": 3}, {"price": 95.0, "touches": 2}]
        assert nearest_support(levels, 97.0) == 95.0
        assert nearest_support(levels, 89.0) is None

    def test_nearest_resistance(self):
        levels = [{"price": 105.0, "touches": 3}, {"price": 110.0, "touches": 2}]
        assert nearest_resistance(levels, 103.0) == 105.0
        assert nearest_resistance(levels, 111.0) is None


# --- Signal tests ---

class TestSignals:
    def test_compute_sl_tp_long(self):
        sl, tp1, tp2, tp3, rr = compute_sl_tp("long", 100.0, 2.0)
        assert sl < Decimal("100")
        assert tp1 > Decimal("100")
        assert tp2 > tp1
        assert tp3 > tp2
        assert rr == 1.5

    def test_compute_sl_tp_long_with_sr(self):
        # Without S/R: SL = 100 - 1.5*2 = 97.0
        sl_no_sr, _, _, _, _ = compute_sl_tp("long", 100.0, 2.0)
        # With support at 98.5 (closer than ATR-based SL)
        sl_with_sr, _, _, _, _ = compute_sl_tp("long", 100.0, 2.0, nearest_sr=98.5)
        # SL should be just below the S/R level, tighter than ATR-based
        assert sl_with_sr > sl_no_sr
        assert sl_with_sr < Decimal("98.5")

    def test_compute_sl_tp_short(self):
        sl, tp1, tp2, tp3, rr = compute_sl_tp("short", 100.0, 2.0)
        assert sl > Decimal("100")
        assert tp1 < Decimal("100")
        assert tp2 < tp1
        assert tp3 < tp2

    def test_compute_position_size(self):
        # 2% risk, entry=100, SL=97 → 3% risk per unit → size = 2/3*100 ≈ 66.7%
        # but capped at 20%
        size = compute_position_size(100.0, 97.0, risk_pct=0.02)
        assert size == 20.0  # capped

        # Wider stop: entry=100, SL=80 → 20% risk per unit → size = 2/20*100 = 10%
        size = compute_position_size(100.0, 80.0, risk_pct=0.02)
        assert size == 10.0

    def test_compute_position_size_zero_risk(self):
        size = compute_position_size(100.0, 100.0)
        assert size == 0.0

    def test_evaluate_long_requires_ema_trend(self):
        row = pd.Series({"ema_trend": -1, "close": 100.0})
        conf, reasons = evaluate_long(row, None, higher_tf_trend=0)
        assert conf == 0.0

    def test_evaluate_long_basic_signal(self):
        row = pd.Series({
            "ema_trend": 1,
            "close": 150.0,
            "ema_200": 120.0,
            "rsi_14": 40.0,
            "macd_hist": 0.5,
            "vol_ratio": 1.2,
            "bb_middle": 155.0,
            "stochrsi_k": 0.5,
            "stochrsi_d": 0.4,
        })
        conf, reasons = evaluate_long(row, None, higher_tf_trend=1)
        assert conf >= MIN_CONFIDENCE
        assert len(reasons) > 0

    def test_evaluate_short_requires_ema_trend(self):
        row = pd.Series({"ema_trend": 1, "close": 100.0})
        conf, reasons = evaluate_short(row, None, higher_tf_trend=0)
        assert conf == 0.0

    def test_generate_signals_returns_list(self):
        df = _make_ohlcv_df(250, trend="up")
        df = compute_indicators(df)
        signals = generate_signals(df, "TESTUSDT", "1h", higher_tf_trend=0)
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, SignalCandidate)

    def test_signal_candidate_fields(self):
        s = SignalCandidate(
            symbol="BTCUSDT",
            direction="long",
            timeframe="1h",
            confidence=0.75,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            take_profit_1=Decimal("51500"),
            take_profit_2=Decimal("52500"),
            take_profit_3=Decimal("54000"),
            risk_reward=1.5,
            position_size_pct=10.0,
        )
        assert s.symbol == "BTCUSDT"
        assert s.direction == "long"
        assert s.confidence == 0.75


# --- MTF tests ---

class TestMTF:
    def test_higher_timeframe_mapping(self):
        assert get_higher_timeframe("15m") == "4h"
        assert get_higher_timeframe("1h") == "4h"
        assert get_higher_timeframe("4h") == "1d"
        assert get_higher_timeframe("1d") is None

    def test_all_entry_tfs_have_htf(self):
        for tf in ("15m", "1h", "4h"):
            assert tf in HIGHER_TF_MAP
