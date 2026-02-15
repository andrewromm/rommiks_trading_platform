"""Signal generation rules, confidence scoring, SL/TP calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
import pandas as pd

# Minimum confidence to emit a signal
MIN_CONFIDENCE = 0.55

# Default risk per trade (% of capital)
DEFAULT_RISK_PCT = 0.02

# ATR multiplier for stop-loss
SL_ATR_MULTIPLIER = 1.5

# R:R ratios for take-profit levels
TP_RR_RATIOS = (1.5, 2.5, 4.0)


@dataclass
class SignalCandidate:
    """Intermediate signal before DB persistence."""

    symbol: str
    direction: str  # "long" or "short"
    timeframe: str
    confidence: float
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal | None
    take_profit_3: Decimal | None
    risk_reward: float
    position_size_pct: float | None
    indicators: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def evaluate_long(
    row: pd.Series,
    prev_row: pd.Series | None,
    higher_tf_trend: int,
) -> tuple[float, list[str]]:
    """Evaluate long signal conditions.

    Returns (confidence, list_of_reasons).
    Returns (0.0, []) if required conditions not met.
    """
    reasons: list[str] = []

    # Required: EMA trend bullish
    if row.get("ema_trend") != 1:
        return 0.0, []

    # Required: price above EMA200 (if available)
    ema_200 = row.get("ema_200")
    if ema_200 is not None and not np.isnan(ema_200) and row["close"] < ema_200:
        return 0.0, []

    confidence = 0.50
    reasons.append("ema_21 > ema_50")

    # RSI in pullback zone (30-50)
    rsi = row.get("rsi_14")
    if rsi is not None and not np.isnan(rsi):
        if 30 <= rsi <= 50:
            confidence += 0.10
            reasons.append(f"rsi_pullback ({rsi:.0f})")
        elif rsi > 70:
            confidence -= 0.10
            reasons.append(f"rsi_overbought ({rsi:.0f})")

    # MACD histogram positive or crossing up
    macd_hist = row.get("macd_hist")
    if macd_hist is not None and not np.isnan(macd_hist):
        if macd_hist > 0:
            confidence += 0.10
            reasons.append("macd_bullish")
        elif prev_row is not None:
            prev_hist = prev_row.get("macd_hist")
            if prev_hist is not None and not np.isnan(prev_hist) and prev_hist < 0:
                confidence += 0.10
                reasons.append("macd_cross_up")

    # Volume confirmation
    vol_ratio = row.get("vol_ratio")
    if vol_ratio is not None and not np.isnan(vol_ratio):
        if vol_ratio > 1.0:
            confidence += 0.10
            reasons.append(f"volume_above_avg ({vol_ratio:.1f}x)")

    # Price near lower Bollinger Band (pullback to mean)
    bb_middle = row.get("bb_middle")
    if bb_middle is not None and not np.isnan(bb_middle):
        if row["close"] < bb_middle:
            confidence += 0.05
            reasons.append("price_below_bb_middle")

    # Stoch RSI K > D (momentum rising)
    stochrsi_k = row.get("stochrsi_k")
    stochrsi_d = row.get("stochrsi_d")
    if (
        stochrsi_k is not None
        and stochrsi_d is not None
        and not np.isnan(stochrsi_k)
        and not np.isnan(stochrsi_d)
    ):
        if stochrsi_k > stochrsi_d:
            confidence += 0.05
            reasons.append("stochrsi_bullish")

    # Higher timeframe alignment
    if higher_tf_trend == 1:
        confidence += 0.10
        reasons.append("htf_trend_aligned")
    elif higher_tf_trend == -1:
        confidence -= 0.15
        reasons.append("htf_trend_conflict")

    return round(max(min(confidence, 0.90), 0.0), 2), reasons


def evaluate_short(
    row: pd.Series,
    prev_row: pd.Series | None,
    higher_tf_trend: int,
) -> tuple[float, list[str]]:
    """Evaluate short signal conditions (mirror of long)."""
    reasons: list[str] = []

    # Required: EMA trend bearish
    if row.get("ema_trend") != -1:
        return 0.0, []

    # Required: price below EMA200 (if available)
    ema_200 = row.get("ema_200")
    if ema_200 is not None and not np.isnan(ema_200) and row["close"] > ema_200:
        return 0.0, []

    confidence = 0.50
    reasons.append("ema_21 < ema_50")

    rsi = row.get("rsi_14")
    if rsi is not None and not np.isnan(rsi):
        if 50 <= rsi <= 70:
            confidence += 0.10
            reasons.append(f"rsi_bounce ({rsi:.0f})")
        elif rsi < 30:
            confidence -= 0.10
            reasons.append(f"rsi_oversold ({rsi:.0f})")

    macd_hist = row.get("macd_hist")
    if macd_hist is not None and not np.isnan(macd_hist):
        if macd_hist < 0:
            confidence += 0.10
            reasons.append("macd_bearish")
        elif prev_row is not None:
            prev_hist = prev_row.get("macd_hist")
            if prev_hist is not None and not np.isnan(prev_hist) and prev_hist > 0:
                confidence += 0.10
                reasons.append("macd_cross_down")

    vol_ratio = row.get("vol_ratio")
    if vol_ratio is not None and not np.isnan(vol_ratio):
        if vol_ratio > 1.0:
            confidence += 0.10
            reasons.append(f"volume_above_avg ({vol_ratio:.1f}x)")

    bb_middle = row.get("bb_middle")
    if bb_middle is not None and not np.isnan(bb_middle):
        if row["close"] > bb_middle:
            confidence += 0.05
            reasons.append("price_above_bb_middle")

    stochrsi_k = row.get("stochrsi_k")
    stochrsi_d = row.get("stochrsi_d")
    if (
        stochrsi_k is not None
        and stochrsi_d is not None
        and not np.isnan(stochrsi_k)
        and not np.isnan(stochrsi_d)
    ):
        if stochrsi_k < stochrsi_d:
            confidence += 0.05
            reasons.append("stochrsi_bearish")

    if higher_tf_trend == -1:
        confidence += 0.10
        reasons.append("htf_trend_aligned")
    elif higher_tf_trend == 1:
        confidence -= 0.15
        reasons.append("htf_trend_conflict")

    return round(max(min(confidence, 0.90), 0.0), 2), reasons


def compute_sl_tp(
    direction: str,
    entry: float,
    atr: float,
    nearest_sr: float | None = None,
) -> tuple[Decimal, Decimal, Decimal | None, Decimal | None, float]:
    """Compute stop-loss and take-profit levels.

    If nearest_sr is provided (support for long, resistance for short),
    SL is placed just beyond it (with ATR/4 buffer) when it's tighter than ATR-based SL.

    Returns (stop_loss, tp1, tp2, tp3, risk_reward).
    """
    atr_risk = SL_ATR_MULTIPLIER * atr
    buffer = atr * 0.25

    if direction == "long":
        atr_sl = entry - atr_risk
        if nearest_sr is not None and nearest_sr > atr_sl:
            # S/R is closer — place SL just below it
            sl = nearest_sr - buffer
        else:
            sl = atr_sl
        risk = entry - sl
        tp1 = entry + TP_RR_RATIOS[0] * risk
        tp2 = entry + TP_RR_RATIOS[1] * risk
        tp3 = entry + TP_RR_RATIOS[2] * risk
    else:
        atr_sl = entry + atr_risk
        if nearest_sr is not None and nearest_sr < atr_sl:
            # S/R is closer — place SL just above it
            sl = nearest_sr + buffer
        else:
            sl = atr_sl
        risk = sl - entry
        tp1 = entry - TP_RR_RATIOS[0] * risk
        tp2 = entry - TP_RR_RATIOS[1] * risk
        tp3 = entry - TP_RR_RATIOS[2] * risk

    return (
        Decimal(str(round(sl, 8))),
        Decimal(str(round(tp1, 8))),
        Decimal(str(round(tp2, 8))),
        Decimal(str(round(tp3, 8))),
        TP_RR_RATIOS[0],
    )


def compute_position_size(
    entry: float,
    sl: float,
    risk_pct: float = DEFAULT_RISK_PCT,
) -> float:
    """Compute position size as % of capital.

    Based on risk amount: if risking 2% of capital and SL is 3% from entry,
    position size = 2/3 * 100 = 66.7% of capital.
    Capped at 20%.
    """
    risk_per_unit = abs(entry - sl) / entry
    if risk_per_unit <= 0:
        return 0.0
    size_pct = risk_pct / risk_per_unit * 100
    return round(min(size_pct, 20.0), 1)


def generate_signals(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    higher_tf_trend: int = 0,
    levels: dict[str, list[dict]] | None = None,
) -> list[SignalCandidate]:
    """Generate trading signals from an indicator-enriched DataFrame.

    Evaluates only the last (most recent) candle.
    Returns a list of 0 or 1 SignalCandidate.
    """
    from src.analyzer.levels import nearest_resistance, nearest_support

    if len(df) < 2:
        return []

    row = df.iloc[-1]
    prev_row = df.iloc[-2]

    atr = row.get("atr_14")
    if atr is None or np.isnan(atr) or atr <= 0:
        return []

    entry = float(row["close"])

    support_levels = levels.get("support", []) if levels else []
    resistance_levels = levels.get("resistance", []) if levels else []

    # Evaluate long
    long_conf, long_reasons = evaluate_long(row, prev_row, higher_tf_trend)
    if long_conf >= MIN_CONFIDENCE:
        sr = nearest_support(support_levels, entry)
        sl, tp1, tp2, tp3, rr = compute_sl_tp("long", entry, float(atr), nearest_sr=sr)
        pos_size = compute_position_size(entry, float(sl))

        indicators_snapshot = _snapshot_indicators(row)

        return [
            SignalCandidate(
                symbol=symbol,
                direction="long",
                timeframe=timeframe,
                confidence=long_conf,
                entry_price=Decimal(str(round(entry, 8))),
                stop_loss=sl,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                risk_reward=rr,
                position_size_pct=pos_size,
                indicators=indicators_snapshot,
                reasons=long_reasons,
            )
        ]

    # Evaluate short
    short_conf, short_reasons = evaluate_short(row, prev_row, higher_tf_trend)
    if short_conf >= MIN_CONFIDENCE:
        sr = nearest_resistance(resistance_levels, entry)
        sl, tp1, tp2, tp3, rr = compute_sl_tp("short", entry, float(atr), nearest_sr=sr)
        pos_size = compute_position_size(entry, float(sl))

        indicators_snapshot = _snapshot_indicators(row)

        return [
            SignalCandidate(
                symbol=symbol,
                direction="short",
                timeframe=timeframe,
                confidence=short_conf,
                entry_price=Decimal(str(round(entry, 8))),
                stop_loss=sl,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                risk_reward=rr,
                position_size_pct=pos_size,
                indicators=indicators_snapshot,
                reasons=short_reasons,
            )
        ]

    return []


def _snapshot_indicators(row: pd.Series) -> dict:
    """Extract key indicator values for the signal record."""
    keys = [
        "ema_9", "ema_21", "ema_50", "ema_200",
        "macd", "macd_signal", "macd_hist",
        "rsi_14", "stochrsi_k", "stochrsi_d",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14", "obv", "vol_sma_20", "vwap",
        "ema_trend", "vol_ratio",
    ]
    result = {}
    for k in keys:
        v = row.get(k)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            result[k] = round(float(v), 8)
    return result
