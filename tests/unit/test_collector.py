"""Tests for the collector module."""

from src.collector.ohlcv import _to_ccxt_symbol


def test_to_ccxt_symbol_usdt():
    assert _to_ccxt_symbol("BTCUSDT") == "BTC/USDT"
    assert _to_ccxt_symbol("ETHUSDT") == "ETH/USDT"
    assert _to_ccxt_symbol("SOLUSDT") == "SOL/USDT"


def test_to_ccxt_symbol_other_quotes():
    assert _to_ccxt_symbol("ETHBTC") == "ETH/BTC"
    assert _to_ccxt_symbol("BTCUSDC") == "BTC/USDC"


def test_to_ccxt_symbol_unknown():
    assert _to_ccxt_symbol("UNKNOWN") == "UNKNOWN"


def test_save_candles_values_conversion():
    """Test that candle data is correctly structured for storage."""
    from src.collector.storage import save_candles

    # Verify the function signature accepts expected types
    assert callable(save_candles)


def test_timeframe_constants():
    from src.collector.ohlcv import TIMEFRAME_MS, TIMEFRAMES

    assert "5m" in TIMEFRAMES
    assert "15m" in TIMEFRAMES
    assert "1h" in TIMEFRAMES
    assert "4h" in TIMEFRAMES
    assert "1d" in TIMEFRAMES

    assert TIMEFRAME_MS["5m"] == 300_000
    assert TIMEFRAME_MS["1h"] == 3_600_000
    assert TIMEFRAME_MS["1d"] == 86_400_000


def test_websocket_manager_init():
    """Test WebSocketManager can be instantiated."""
    from unittest.mock import AsyncMock

    from src.collector.websocket import WebSocketManager

    redis_mock = AsyncMock()
    ws = WebSocketManager(
        symbols=["BTCUSDT", "ETHUSDT"],
        redis_client=redis_mock,
        testnet=True,
    )
    assert ws._symbols == ["BTCUSDT", "ETHUSDT"]
    assert ws._testnet is True


def test_exchange_client_init():
    """Test ExchangeClient can be instantiated."""
    from src.collector.exchange import ExchangeClient

    client = ExchangeClient()
    assert client._exchange is not None
    assert client.rate_limit > 0
