"""Multi-timeframe analysis — determine higher TF trend for signal confirmation."""

import pandas as pd

from src.analyzer.indicators import compute_indicators
from src.core.logger import get_logger

log = get_logger("analyzer.mtf")

# Mapping: working timeframe → higher timeframe for trend confirmation
HIGHER_TF_MAP: dict[str, str] = {
    "5m": "1h",
    "15m": "4h",
    "1h": "4h",
    "4h": "1d",
}

# Minimum candles needed to compute indicators on higher TF
MIN_CANDLES_HTF = 210  # enough for EMA(200) + some buffer


def get_higher_timeframe(timeframe: str) -> str | None:
    """Return the higher timeframe for trend confirmation."""
    return HIGHER_TF_MAP.get(timeframe)


def compute_htf_trend(htf_df: pd.DataFrame) -> int:
    """Compute trend direction from a higher-timeframe OHLCV DataFrame.

    Returns:
        1  = bullish (EMA21 > EMA50, price > EMA200)
       -1  = bearish (EMA21 < EMA50, price < EMA200)
        0  = neutral / mixed / insufficient data
    """
    if len(htf_df) < MIN_CANDLES_HTF:
        log.debug("htf_insufficient_data", candles=len(htf_df), required=MIN_CANDLES_HTF)
        return 0

    df = compute_indicators(htf_df)
    last = df.iloc[-1]

    ema_21 = last.get("ema_21")
    ema_50 = last.get("ema_50")
    ema_200 = last.get("ema_200")

    if any(v is None or pd.isna(v) for v in (ema_21, ema_50, ema_200)):
        return 0

    close = last["close"]

    ema_bullish = ema_21 > ema_50
    above_200 = close > ema_200

    if ema_bullish and above_200:
        return 1
    if not ema_bullish and not above_200:
        return -1
    return 0
