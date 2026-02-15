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

    return out
