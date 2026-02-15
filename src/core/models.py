import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OHLCV(Base):
    __tablename__ = "ohlcv"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection))
    timeframe: Mapped[str] = mapped_column(String(5))
    confidence: Mapped[float] = mapped_column(Float)  # 0.0 - 1.0
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    take_profit_1: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    take_profit_2: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit_3: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    risk_reward: Mapped[float] = mapped_column(Float)
    position_size_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50))  # "technical", "scoring", etc.
    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.NEW)
    indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        """Convert Signal to dict for formatter/notifier."""
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "timeframe": self.timeframe,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "take_profit_3": self.take_profit_3,
            "risk_reward": self.risk_reward,
            "position_size_pct": self.position_size_pct,
            "indicators": self.indicators or {},
        }


class SentimentData(Base):
    __tablename__ = "sentiment_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(50))  # "lunarcrush", "news", "fear_greed"
    score: Mapped[float] = mapped_column(Float)  # -1.0 to 1.0
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WhaleTransaction(Base):
    __tablename__ = "whale_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(100), unique=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    from_type: Mapped[str] = mapped_column(String(20))  # "exchange", "whale", "unknown"
    to_type: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(20))  # "inflow", "outflow", "transfer"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    size_usdt: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("signals.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
