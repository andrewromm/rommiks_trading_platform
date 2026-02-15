"""Support and resistance level detection via swing highs/lows."""

import numpy as np
import pandas as pd


def find_swing_highs(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Find swing high points where high is the max in a 2*window+1 range."""
    highs = df["high"]
    rolling_max = highs.rolling(window=2 * window + 1, center=True).max()
    mask = highs == rolling_max
    return highs[mask]


def find_swing_lows(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """Find swing low points where low is the min in a 2*window+1 range."""
    lows = df["low"]
    rolling_min = lows.rolling(window=2 * window + 1, center=True).min()
    mask = lows == rolling_min
    return lows[mask]


def _cluster_levels(values: list[float], tolerance_pct: float) -> list[dict]:
    """Group nearby price levels into clusters.

    Returns list of {price, touches} sorted by touches descending.
    """
    if not values:
        return []

    sorted_vals = sorted(values)
    clusters: list[list[float]] = []
    current: list[float] = [sorted_vals[0]]

    for v in sorted_vals[1:]:
        center = np.mean(current)
        if abs(v - center) / center <= tolerance_pct / 100:
            current.append(v)
        else:
            clusters.append(current)
            current = [v]
    clusters.append(current)

    result = [
        {"price": round(float(np.mean(c)), 8), "touches": len(c)}
        for c in clusters
    ]
    result.sort(key=lambda x: x["touches"], reverse=True)
    return result


def find_support_resistance(
    df: pd.DataFrame,
    window: int = 5,
    tolerance_pct: float = 0.5,
    max_levels: int = 10,
) -> dict[str, list[dict]]:
    """Detect support and resistance levels from OHLCV data.

    Returns {"support": [...], "resistance": [...]} where each entry
    has "price" and "touches" keys.
    """
    swing_highs = find_swing_highs(df, window).dropna().tolist()
    swing_lows = find_swing_lows(df, window).dropna().tolist()

    resistance = _cluster_levels(swing_highs, tolerance_pct)[:max_levels]
    support = _cluster_levels(swing_lows, tolerance_pct)[:max_levels]

    return {"support": support, "resistance": resistance}


def nearest_support(levels: list[dict], price: float) -> float | None:
    """Find nearest support level below the given price."""
    below = [lv["price"] for lv in levels if lv["price"] < price]
    return max(below) if below else None


def nearest_resistance(levels: list[dict], price: float) -> float | None:
    """Find nearest resistance level above the given price."""
    above = [lv["price"] for lv in levels if lv["price"] > price]
    return min(above) if above else None
