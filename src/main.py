import asyncio
import signal

from src.core.config import settings
from src.core.database import close_db, init_db
from src.core.logger import get_logger, setup_logging
from src.core.redis import close_redis, init_redis

log = get_logger("main")

shutdown_event = asyncio.Event()


def handle_shutdown(sig: signal.Signals) -> None:
    log.info("shutdown_signal_received", signal=sig.name)
    shutdown_event.set()


async def main() -> None:
    setup_logging(settings.log_level)
    log.info(
        "starting_trading_system",
        environment=settings.environment,
        testnet=settings.bybit_testnet,
    )

    # Init infrastructure
    await init_db()
    log.info("database_connected")

    await init_redis()
    log.info("redis_connected")

    log.info("system_ready")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Graceful shutdown
    log.info("shutting_down")
    await close_redis()
    await close_db()
    log.info("shutdown_complete")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown, sig)

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
