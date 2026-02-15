import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class SignalDirection(enum.StrEnum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class SignalStatus(enum.StrEnum):
    NEW = "new"
    ACTIVE = "active"
    EXPIRED = "expired"
    HIT_TP = "hit_tp"
    HIT_SL = "hit_sl"
    CANCELLED = "cancelled"


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. "BTCUSDT"
    base: Mapped[str] = mapped_column(String(10))  # e.g. "BTC"
    quote: Mapped[str] = mapped_column(String(10))  # e.g. "USDT"
    is_active: Mapped[bool] = mapped_column(default=True)
    min_order_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class OHLCV(Base):
    __tablename__ = "ohlcv"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(5))  # "5m", "15m", "1h", "4h", "1d"
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_ohlcv_symbol_tf_ts"),
        Index("ix_ohlcv_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection))
    timeframe: Mapped[str] = mapped_column(String(5))
    confidence: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit_1: Mapped[float] = mapped_column(Float)
    take_profit_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_3: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float] = mapped_column(Float)
    position_size_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50))  # "technical", "scoring", etc.
    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.NEW)
    indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SentimentData(Base):
    __tablename__ = "sentiment_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(50))  # "lunarcrush", "news", "fear_greed"
    score: Mapped[float] = mapped_column(Float)  # -1.0 to 1.0
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WhaleTransaction(Base):
    __tablename__ = "whale_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(100), unique=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    from_type: Mapped[str] = mapped_column(String(20))  # "exchange", "whale", "unknown"
    to_type: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(20))  # "inflow", "outflow", "transfer"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_usdt: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
