"""WebSocket manager for real-time ByBit kline and ticker data."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from src.core.logger import get_logger

# ByBit interval string → standard timeframe string
BYBIT_INTERVAL_MAP: dict[str, str] = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "360": "6h",
    "720": "12h",
    "D": "1d",
    "W": "1w",
    "M": "1M",
}

log = get_logger("collector.websocket")

# ByBit WebSocket endpoints
WS_PUBLIC_MAINNET = "wss://stream.bybit.com/v5/public/spot"
WS_PUBLIC_TESTNET = "wss://stream-testnet.bybit.com/v5/public/spot"

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 20
RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60
STATS_LOG_INTERVAL = 300  # log message stats every 5 minutes


class WebSocketManager:
    """Manages WebSocket connections to ByBit for real-time data.

    Subscribes to kline (candle) and ticker updates,
    stores ticker data in Redis for fast access.
    """

    def __init__(
        self,
        symbols: list[str],
        redis_client: redis.Redis,
        testnet: bool = True,
        kline_timeframes: list[str] | None = None,
        on_kline: Callable[[str, str, list], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._symbols = symbols
        self._redis = redis_client
        self._testnet = testnet
        self._ws_url = WS_PUBLIC_TESTNET if testnet else WS_PUBLIC_MAINNET
        self._running = False
        self._reconnect_delay = RECONNECT_DELAY
        self._msg_count = 0
        self._last_msg_at: datetime | None = None
        self._kline_timeframes = kline_timeframes or []
        self._on_kline = on_kline

    async def start(self, shutdown_event: asyncio.Event) -> None:
        """Run WebSocket connection with auto-reconnect."""
        import contextlib

        self._running = True
        log.info("ws_starting", symbols=len(self._symbols), url=self._ws_url)

        heartbeat_task = asyncio.create_task(self._heartbeat_loop(shutdown_event))
        try:
            while self._running and not shutdown_event.is_set():
                try:
                    await self._connect_and_listen(shutdown_event)
                except Exception:
                    if not self._running or shutdown_event.is_set():
                        break
                    log.exception(
                        "ws_connection_error",
                        reconnect_in=self._reconnect_delay,
                    )
                    try:
                        await asyncio.wait_for(
                            shutdown_event.wait(), timeout=self._reconnect_delay
                        )
                        break  # shutdown requested during wait
                    except TimeoutError:
                        pass
                    # Exponential backoff
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, MAX_RECONNECT_DELAY
                    )
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

        log.info("ws_stopped")

    def stop(self) -> None:
        """Signal the WebSocket to stop."""
        self._running = False

    async def _heartbeat_loop(self, shutdown_event: asyncio.Event) -> None:
        """Log message stats every STATS_LOG_INTERVAL seconds."""
        while self._running and not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=STATS_LOG_INTERVAL)
                break  # shutdown requested
            except TimeoutError:
                pass
            log.info(
                "ws_stats",
                messages_processed=self._msg_count,
                last_message_at=self._last_msg_at.isoformat() if self._last_msg_at else None,
                symbols=len(self._symbols),
            )
            self._msg_count = 0

    async def _connect_and_listen(self, shutdown_event: asyncio.Event) -> None:
        """Connect to WebSocket, subscribe, and process messages."""
        try:
            import websockets
        except ImportError:
            log.error("websockets_not_installed", hint="poetry add websockets")
            return

        async with websockets.connect(self._ws_url, ping_interval=HEARTBEAT_INTERVAL) as ws:
            log.info("ws_connected")
            self._reconnect_delay = RECONNECT_DELAY  # reset on success

            # Subscribe to tickers
            await self._subscribe(ws, shutdown_event)

            # Listen for messages
            async for raw_msg in ws:
                if shutdown_event.is_set():
                    break
                try:
                    msg = json.loads(raw_msg)
                    await self._handle_message(msg)
                except Exception:
                    log.exception("ws_message_error")

    async def _subscribe(self, ws: Any, shutdown_event: asyncio.Event) -> None:
        """Send subscription requests for tickers and klines."""
        topics: list[str] = [f"tickers.{s}" for s in self._symbols]

        if self._kline_timeframes:
            topics += [
                f"kline.{tf}.{s}"
                for s in self._symbols
                for tf in self._kline_timeframes
            ]

        # ByBit allows max 10 topics per subscribe message
        for i in range(0, len(topics), 10):
            batch = topics[i : i + 10]
            sub_msg = {"op": "subscribe", "args": batch}
            await ws.send(json.dumps(sub_msg))
            log.info("ws_subscribed", topics=len(batch))
            if shutdown_event.is_set():
                break

    async def _handle_message(self, msg: dict) -> None:
        """Route incoming WebSocket messages."""
        topic = msg.get("topic", "")

        self._msg_count += 1
        self._last_msg_at = datetime.now(UTC)

        if topic.startswith("tickers."):
            await self._handle_ticker(msg)
        elif topic.startswith("kline."):
            await self._handle_kline(msg)
        elif msg.get("op") == "subscribe":
            success = msg.get("success", False)
            if not success:
                log.warning("ws_subscribe_failed", msg=msg)
        elif msg.get("op") == "pong" or msg.get("ret_msg") == "pong":
            pass  # heartbeat response
        elif "success" not in msg and "topic" not in msg:
            log.debug("ws_unknown_message", msg=msg)

    async def _handle_ticker(self, msg: dict) -> None:
        """Process ticker update and cache in Redis."""
        data = msg.get("data", {})
        symbol = data.get("symbol", "")
        if not symbol:
            return

        ticker_data = {
            "symbol": symbol,
            "last_price": data.get("lastPrice", ""),
            "price_24h_pct": data.get("price24hPcnt", ""),
            "high_24h": data.get("highPrice24h", ""),
            "low_24h": data.get("lowPrice24h", ""),
            "volume_24h": data.get("volume24h", ""),
            "turnover_24h": data.get("turnover24h", ""),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Store in Redis with 60s TTL (atomic via pipeline)
        key = f"ticker:{symbol}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=ticker_data)
            pipe.expire(key, 60)
            await pipe.execute()

    async def _handle_kline(self, msg: dict) -> None:
        """Process confirmed kline (candle) and call on_kline callback."""
        if self._on_kline is None:
            return

        topic = msg.get("topic", "")
        # topic format: "kline.{interval}.{symbol}"
        parts = topic.split(".", 2)
        if len(parts) != 3:
            log.debug("ws_kline_bad_topic", topic=topic)
            return

        _, interval, symbol = parts
        timeframe = BYBIT_INTERVAL_MAP.get(interval)
        if not timeframe:
            log.debug("ws_kline_unknown_interval", interval=interval)
            return

        for candle_data in msg.get("data", []):
            # Only process confirmed (closed) candles
            if not candle_data.get("confirm", False):
                continue

            try:
                # Convert to ccxt-compatible format: [ts_ms, open, high, low, close, volume]
                candle = [
                    int(candle_data["start"]),
                    float(candle_data["open"]),
                    float(candle_data["high"]),
                    float(candle_data["low"]),
                    float(candle_data["close"]),
                    float(candle_data["volume"]),
                ]
                await self._on_kline(symbol, timeframe, candle)
            except (KeyError, ValueError, TypeError):
                log.exception("ws_kline_parse_error", topic=topic)
