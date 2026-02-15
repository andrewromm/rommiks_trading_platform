"""Coin screener — rank symbols by trading potential."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analyzer.indicators import compute_indicators
from src.core.database import async_session
from src.core.logger import get_logger
from src.core.models import OHLCV, Symbol

log = get_logger("screener")

# Minimum candles needed for screener analysis
MIN_CANDLES_SCREEN = 50

# Minimum 24h volume in USD to include a symbol
MIN_VOLUME_24H_USD = 1_000_000

# Weights for composite score
WEIGHT_TREND = 30
WEIGHT_VOLUME = 25
WEIGHT_VOLATILITY = 20
WEIGHT_RSI_SETUP = 25


async def get_active_symbols(session: AsyncSession) -> list[str]:
    """Get list of active symbols that have enough OHLCV data."""
    result = await session.execute(
        select(Symbol.name).where(Symbol.is_active.is_(True)).order_by(Symbol.name)
    )
    return [row[0] for row in result.all()]


async def load_daily_ohlcv(
    session: AsyncSession,
    symbol: str,
    timeframe: str = "1h",
    limit: int = MIN_CANDLES_SCREEN,
) -> pd.DataFrame:
    """Load recent OHLCV for screener analysis."""
    result = await session.execute(
        select(
            OHLCV.timestamp, OHLCV.open, OHLCV.high,
            OHLCV.low, OHLCV.close, OHLCV.volume,
        )
        .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.timestamp.desc())
        .limit(limit)
    )
    rows = result.all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df.sort_values("timestamp").reset_index(drop=True)


def compute_score(df: pd.DataFrame) -> dict:
    """Compute screener score for a single symbol.

    Returns dict with score breakdown and metadata.
    """
    if len(df) < MIN_CANDLES_SCREEN:
        return {"score": 0, "skip": True}

    df = compute_indicators(df)
    last = df.iloc[-1]

    # --- Trend score (0-100) ---
    ema_21 = last.get("ema_21")
    ema_50 = last.get("ema_50")
    ema_200 = last.get("ema_200")
    close = last["close"]

    trend_score = 50  # neutral baseline
    if ema_21 is not None and ema_50 is not None:
        if not np.isnan(ema_21) and not np.isnan(ema_50):
            if ema_21 > ema_50:
                trend_score += 25
            else:
                trend_score -= 25
    if ema_200 is not None and not np.isnan(ema_200):
        if close > ema_200:
            trend_score += 25
        else:
            trend_score -= 25
    trend_score = max(min(trend_score, 100), 0)

    # Trend direction label
    if trend_score >= 70:
        trend_label = "bullish"
    elif trend_score <= 30:
        trend_label = "bearish"
    else:
        trend_label = "neutral"

    # --- Volume score (0-100) ---
    vol_ratio = last.get("vol_ratio")
    if vol_ratio is not None and not np.isnan(vol_ratio):
        # vol_ratio > 2.0 = 100, vol_ratio 1.0 = 50, vol_ratio 0.5 = 25
        volume_score = min(vol_ratio * 50, 100)
    else:
        volume_score = 50

    # --- Volatility score (0-100) ---
    atr = last.get("atr_14")
    if atr is not None and not np.isnan(atr) and close > 0:
        atr_pct = (atr / close) * 100
        # Ideal range 1-3% ATR for day trading
        if 1.0 <= atr_pct <= 3.0:
            volatility_score = 100
        elif atr_pct < 1.0:
            volatility_score = atr_pct * 100  # 0-100 linearly
        else:
            # Too volatile (>3%), diminishing score
            volatility_score = max(100 - (atr_pct - 3.0) * 20, 20)
    else:
        volatility_score = 50

    # --- RSI setup score (0-100) ---
    rsi = last.get("rsi_14")
    if rsi is not None and not np.isnan(rsi):
        # Best setups: RSI 30-50 (pullback buy) or RSI 50-70 (trend continuation)
        if 30 <= rsi <= 50:
            rsi_score = 90  # pullback in uptrend
        elif 50 < rsi <= 65:
            rsi_score = 70  # trend continuation
        elif 65 < rsi <= 80:
            rsi_score = 40  # overbought risk
        elif rsi < 30:
            rsi_score = 60  # oversold potential reversal
        else:
            rsi_score = 20  # extreme overbought
    else:
        rsi_score = 50

    # --- Composite score ---
    composite = (
        trend_score * WEIGHT_TREND
        + volume_score * WEIGHT_VOLUME
        + volatility_score * WEIGHT_VOLATILITY
        + rsi_score * WEIGHT_RSI_SETUP
    ) / (WEIGHT_TREND + WEIGHT_VOLUME + WEIGHT_VOLATILITY + WEIGHT_RSI_SETUP)

    # Estimate 24h volume in USD
    vol_24h = float(df.tail(24)["volume"].sum() * close) if len(df) >= 24 else 0

    return {
        "score": round(composite, 1),
        "trend": trend_label,
        "trend_score": round(trend_score, 1),
        "volume_score": round(volume_score, 1),
        "volatility_score": round(volatility_score, 1),
        "rsi_score": round(rsi_score, 1),
        "rsi": round(float(rsi), 1) if rsi is not None and not np.isnan(rsi) else None,
        "volume_24h_usd": round(vol_24h, 0),
        "close": float(close),
        "skip": False,
    }


async def run_screener(
    timeframe: str = "1h",
    top_n: int = 10,
    min_volume_usd: float = MIN_VOLUME_24H_USD,
) -> list[dict]:
    """Run screener across all active symbols.

    Returns top_n ranked symbols with scores.
    """
    async with async_session() as session:
        symbols = await get_active_symbols(session)

        if not symbols:
            log.warning("screener_no_symbols")
            return []

        results: list[dict] = []

        for symbol in symbols:
            try:
                df = await load_daily_ohlcv(session, symbol, timeframe)

                if df.empty or len(df) < MIN_CANDLES_SCREEN:
                    continue

                score_data = compute_score(df)
                if score_data.get("skip"):
                    continue

                # Volume filter
                if score_data["volume_24h_usd"] < min_volume_usd:
                    continue

                score_data["symbol"] = symbol
                results.append(score_data)
            except Exception:
                log.exception("screener_error", symbol=symbol)

    # Sort by composite score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    log.info(
        "screener_complete",
        total_symbols=len(symbols),
        qualified=len(results),
        top_n=top_n,
    )

    return results[:top_n]
