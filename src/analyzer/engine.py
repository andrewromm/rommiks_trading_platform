"""Analysis engine — orchestrates indicator calculation and signal generation."""

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analyzer.indicators import compute_indicators
from src.analyzer.levels import find_support_resistance
from src.analyzer.mtf import MIN_CANDLES_HTF, compute_htf_trend, get_higher_timeframe
from src.analyzer.signals import SignalCandidate, generate_signals
from src.core.database import async_session
from src.core.logger import get_logger
from src.core.models import OHLCV, Signal, SignalDirection, SignalStatus

log = get_logger("analyzer.engine")

# Minimum candles for analysis on the working timeframe
MIN_CANDLES = 210

# Cooldown: no more than 1 signal per symbol/timeframe within this window
SIGNAL_COOLDOWN_HOURS = 4

# Signal expiry in hours (per timeframe)
SIGNAL_EXPIRY: dict[str, int] = {
    "5m": 1,
    "15m": 4,
    "1h": 12,
    "4h": 48,
    "1d": 168,
}

# Timeframes to analyze for signals (entry timeframes)
ENTRY_TIMEFRAMES = ["15m", "1h", "4h"]

# Adjacent timeframes to check for MTF confluence per entry timeframe
CONFLUENCE_TIMEFRAMES: dict[str, list[str]] = {
    "15m": ["1h", "4h"],
    "1h": ["4h"],
    "4h": ["1d"],
}

# Minimum candles for confluence timeframe analysis
MIN_CANDLES_CONFLUENCE = 100

# Confidence boost per agreeing timeframe
CONFLUENCE_BOOST_PER_TF = 0.08


async def load_ohlcv(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    limit: int = MIN_CANDLES,
) -> pd.DataFrame:
    """Load OHLCV data from DB into a pandas DataFrame."""
    result = await session.execute(
        select(
            OHLCV.timestamp,
            OHLCV.open,
            OHLCV.high,
            OHLCV.low,
            OHLCV.close,
            OHLCV.volume,
        )
        .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.timestamp.desc())
        .limit(limit)
    )
    rows = result.all()

    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


async def check_cooldown(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
) -> bool:
    """Check if a signal was recently generated (within cooldown window).

    Returns True if cooldown is active (should NOT generate new signal).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=SIGNAL_COOLDOWN_HOURS)
    result = await session.execute(
        select(Signal.id)
        .where(
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.source == "technical_analysis",
            Signal.created_at >= cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def save_signal(session: AsyncSession, candidate: SignalCandidate) -> Signal:
    """Persist a SignalCandidate to the database."""
    expiry_hours = SIGNAL_EXPIRY.get(candidate.timeframe, 12)

    signal = Signal(
        symbol=candidate.symbol,
        direction=SignalDirection(candidate.direction),
        timeframe=candidate.timeframe,
        confidence=candidate.confidence,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        take_profit_1=candidate.take_profit_1,
        take_profit_2=candidate.take_profit_2,
        take_profit_3=candidate.take_profit_3,
        risk_reward=candidate.risk_reward,
        position_size_pct=candidate.position_size_pct,
        source="technical_analysis",
        status=SignalStatus.NEW,
        indicators=candidate.indicators,
        expires_at=datetime.now(UTC) + timedelta(hours=expiry_hours),
    )
    session.add(signal)
    await session.commit()
    await session.refresh(signal)
    return signal


def _quick_signal_direction(df: pd.DataFrame, htf_trend: int = 0) -> str | None:
    """Compute indicators and return signal direction without DB interaction.

    Returns "long", "short", or None if no signal above MIN_CONFIDENCE.
    Used for MTF confluence scoring only — does not save anything.
    """
    if len(df) < 50:
        return None

    try:
        enriched = compute_indicators(df)
        levels = find_support_resistance(enriched)
        candidates = generate_signals(enriched, "", "", higher_tf_trend=htf_trend, levels=levels)
        if candidates:
            return candidates[0].direction
    except Exception:
        pass
    return None


async def analyze_symbol(
    symbol: str,
    timeframe: str,
) -> list[Signal]:
    """Run full analysis on a single symbol/timeframe and save signals.

    Creates its own DB session. Returns list of saved signals (0 or 1).
    """
    saved: list[Signal] = []

    # Read phase: single session for cooldown check + data loading
    async with async_session() as session:
        if await check_cooldown(session, symbol, timeframe):
            log.debug("signal_cooldown_active", symbol=symbol, timeframe=timeframe)
            return []

        df = await load_ohlcv(session, symbol, timeframe)

        htf_df = None
        htf = get_higher_timeframe(timeframe)
        if htf:
            htf_df = await load_ohlcv(session, symbol, htf, limit=MIN_CANDLES_HTF)

        # Load confluence timeframes
        confluence_dfs: dict[str, pd.DataFrame] = {}
        for ctf in CONFLUENCE_TIMEFRAMES.get(timeframe, []):
            ctf_df = await load_ohlcv(session, symbol, ctf, limit=MIN_CANDLES_CONFLUENCE)
            if len(ctf_df) >= 50:
                confluence_dfs[ctf] = ctf_df

    if len(df) < MIN_CANDLES:
        log.debug(
            "insufficient_data",
            symbol=symbol,
            timeframe=timeframe,
            candles=len(df),
            required=MIN_CANDLES,
        )
        return []

    # Compute phase: pure CPU work, no DB needed
    df = compute_indicators(df)
    levels = find_support_resistance(df)

    htf_trend = 0
    if htf_df is not None and len(htf_df) >= MIN_CANDLES_HTF:
        htf_trend = compute_htf_trend(htf_df)

    candidates = generate_signals(
        df, symbol, timeframe, higher_tf_trend=htf_trend, levels=levels
    )

    # Apply MTF confluence boost
    if candidates and confluence_dfs:
        candidate = candidates[0]
        agreements = sum(
            1
            for ctf_df in confluence_dfs.values()
            if _quick_signal_direction(ctf_df, htf_trend) == candidate.direction
        )
        if agreements > 0:
            boost = round(min(agreements * CONFLUENCE_BOOST_PER_TF, 0.20), 2)
            candidate.confidence = round(min(candidate.confidence + boost, 0.90), 2)
            candidate.reasons.append(f"mtf_confluence ({agreements}/{len(confluence_dfs)})")
            log.debug(
                "mtf_confluence_boost",
                symbol=symbol,
                timeframe=timeframe,
                agreements=agreements,
                boost=boost,
            )

    # Write phase: single session for saving signals
    if candidates:
        async with async_session() as session:
            for candidate in candidates:
                candidate.indicators["levels"] = levels
                candidate.indicators["reasons"] = candidate.reasons
                signal = await save_signal(session, candidate)
                saved.append(signal)
                log.info(
                    "signal_generated",
                    symbol=symbol,
                    direction=candidate.direction,
                    timeframe=timeframe,
                    confidence=candidate.confidence,
                    entry=str(candidate.entry_price),
                    signal_id=signal.id,
                )

    return saved


async def analyze_all(
    symbols: list[str],
    timeframes: list[str] | None = None,
) -> list[Signal]:
    """Analyze multiple symbols across timeframes.

    Returns list of all generated signals.
    """
    if timeframes is None:
        timeframes = ENTRY_TIMEFRAMES

    all_signals: list[Signal] = []
    total_pairs = len(symbols) * len(timeframes)
    completed = 0

    for symbol in symbols:
        for tf in timeframes:
            try:
                signals = await analyze_symbol(symbol, tf)
                all_signals.extend(signals)
            except Exception:
                log.exception("analyze_error", symbol=symbol, timeframe=tf)
            completed += 1
            if completed % 20 == 0:
                log.info("analyze_progress", completed=completed, total=total_pairs)

    log.info(
        "analyze_all_complete",
        symbols=len(symbols),
        timeframes=timeframes,
        signals_generated=len(all_signals),
    )
    return all_signals
