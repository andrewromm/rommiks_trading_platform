"""Technical indicators computed on OHLCV DataFrames."""

import numpy as np
import pandas as pd
import ta


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume.
    Returns a new DataFrame with indicator columns added.
    """
    out = df.copy()

    close = out["close"]
    high = out["high"]
    low = out["low"]
    volume = out["volume"]

    # --- Trend: EMA ---
    for period in (9, 21, 50, 200):
        out[f"ema_{period}"] = ta.trend.ema_indicator(close, window=period)

    # --- Trend: MACD(12, 26, 9) ---
    macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    out["macd"] = macd.macd()
    out["macd_signal"] = macd.macd_signal()
    out["macd_hist"] = macd.macd_diff()

    # --- Momentum: RSI(14) ---
    out["rsi_14"] = ta.momentum.rsi(close, window=14)

    # --- Momentum: Stochastic RSI ---
    stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    out["stochrsi_k"] = stoch_rsi.stochrsi_k()
    out["stochrsi_d"] = stoch_rsi.stochrsi_d()

    # --- Volatility: Bollinger Bands(20, 2) ---
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    out["bb_upper"] = bb.bollinger_hband()
    out["bb_middle"] = bb.bollinger_mavg()
    out["bb_lower"] = bb.bollinger_lband()

    # --- Volatility: ATR(14) ---
    out["atr_14"] = ta.volatility.average_true_range(high, low, close, window=14)

    # --- Volume: OBV ---
    out["obv"] = ta.volume.on_balance_volume(close, volume)

    # --- Volume: SMA(20) ---
    out["vol_sma_20"] = ta.trend.sma_indicator(volume, window=20)

    # --- Volume: VWAP (cumulative, resets not implemented — use session-level) ---
    typical_price = (high + low + close) / 3
    cum_vol = volume.cumsum()
    cum_tp_vol = (typical_price * volume).cumsum()
    out["vwap"] = np.where(cum_vol > 0, cum_tp_vol / cum_vol, np.nan)

    # --- Derived: trend direction from EMA crossover ---
    out["ema_trend"] = np.where(
        out["ema_21"] > out["ema_50"],
        1,
        np.where(out["ema_21"] < out["ema_50"], -1, 0),
    )

    # --- Derived: volume ratio ---
    out["vol_ratio"] = np.where(
        out["vol_sma_20"] > 0, volume / out["vol_sma_20"], np.nan
    )

    # --- Candlestick patterns ---
    out = _add_candlestick_patterns(out)

    return out


def _add_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Add candlestick pattern boolean columns to an indicator DataFrame.

    Columns added: cdl_doji, cdl_hammer, cdl_shooting_star,
    cdl_bullish_engulfing, cdl_bearish_engulfing.
    """
    o = df["open"]
    h = df["high"]
    low = df["low"]
    c = df["close"]

    body = (c - o).abs()
    candle_range = h - low
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - low

    # Doji: body < 10% of candle range
    df["cdl_doji"] = (candle_range > 0) & (body < 0.1 * candle_range)

    # Hammer: long lower shadow (>2x body), small upper shadow (<= body), body > 0
    df["cdl_hammer"] = (
        (body > 0)
        & (lower_shadow > 2 * body)
        & (upper_shadow <= body)
    )

    # Shooting Star: long upper shadow (>2x body), small lower shadow (<= body), body > 0
    df["cdl_shooting_star"] = (
        (body > 0)
        & (upper_shadow > 2 * body)
        & (lower_shadow <= body)
    )

    # Bullish Engulfing: prev bearish candle fully engulfed by current bullish candle
    prev_o = o.shift(1)
    prev_c = c.shift(1)
    df["cdl_bullish_engulfing"] = (
        (prev_c < prev_o)   # previous candle is bearish
        & (c > o)           # current candle is bullish
        & (o <= prev_c)     # current open <= prev close
        & (c >= prev_o)     # current close >= prev open
    )

    # Bearish Engulfing: prev bullish candle fully engulfed by current bearish candle
    df["cdl_bearish_engulfing"] = (
        (prev_c > prev_o)   # previous candle is bullish
        & (c < o)           # current candle is bearish
        & (o >= prev_c)     # current open >= prev close
        & (c <= prev_o)     # current close <= prev open
    )

    return df


def detect_divergences(df: pd.DataFrame, window: int = 5) -> dict[str, bool]:
    """Detect RSI and MACD divergences using swing highs/lows.

    Returns a dict with keys:
      bullish_rsi  — price lower low, RSI higher low  (bullish reversal signal)
      bearish_rsi  — price higher high, RSI lower high (bearish reversal signal)
      bullish_macd — price lower low, MACD hist higher low
      bearish_macd — price higher high, MACD hist lower high

    Requires at least 2 swing points of each type to detect divergence.
    Returns all False if insufficient data.
    """
    from src.analyzer.levels import find_swing_highs, find_swing_lows

    result: dict[str, bool] = {
        "bullish_rsi": False,
        "bearish_rsi": False,
        "bullish_macd": False,
        "bearish_macd": False,
    }

    if len(df) < window * 4:
        return result

    close = df["close"]
    rsi = df.get("rsi_14")
    macd_hist = df.get("macd_hist")

    # --- Bullish divergences (swing lows) ---
    swing_low_mask = find_swing_lows(df, window)
    swing_low_idx = swing_low_mask.dropna().index.tolist()

    if len(swing_low_idx) >= 2:
        prev_idx, last_idx = swing_low_idx[-2], swing_low_idx[-1]
        prev_price, last_price = close[prev_idx], close[last_idx]

        if last_price < prev_price:  # price making lower low
            if rsi is not None:
                prev_rsi, last_rsi = rsi.get(prev_idx), rsi.get(last_idx)
                if (
                    prev_rsi is not None
                    and last_rsi is not None
                    and not np.isnan(prev_rsi)
                    and not np.isnan(last_rsi)
                    and last_rsi > prev_rsi  # RSI making higher low
                ):
                    result["bullish_rsi"] = True

            if macd_hist is not None:
                prev_macd, last_macd = macd_hist.get(prev_idx), macd_hist.get(last_idx)
                if (
                    prev_macd is not None
                    and last_macd is not None
                    and not np.isnan(prev_macd)
                    and not np.isnan(last_macd)
                    and last_macd > prev_macd  # MACD hist making higher low
                ):
                    result["bullish_macd"] = True

    # --- Bearish divergences (swing highs) ---
    swing_high_mask = find_swing_highs(df, window)
    swing_high_idx = swing_high_mask.dropna().index.tolist()

    if len(swing_high_idx) >= 2:
        prev_idx, last_idx = swing_high_idx[-2], swing_high_idx[-1]
        prev_price, last_price = close[prev_idx], close[last_idx]

        if last_price > prev_price:  # price making higher high
            if rsi is not None:
                prev_rsi, last_rsi = rsi.get(prev_idx), rsi.get(last_idx)
                if (
                    prev_rsi is not None
                    and last_rsi is not None
                    and not np.isnan(prev_rsi)
                    and not np.isnan(last_rsi)
                    and last_rsi < prev_rsi  # RSI making lower high
                ):
                    result["bearish_rsi"] = True

            if macd_hist is not None:
                prev_macd, last_macd = macd_hist.get(prev_idx), macd_hist.get(last_idx)
                if (
                    prev_macd is not None
                    and last_macd is not None
                    and not np.isnan(prev_macd)
                    and not np.isnan(last_macd)
                    and last_macd < prev_macd  # MACD hist making lower high
                ):
                    result["bearish_macd"] = True

    return result
