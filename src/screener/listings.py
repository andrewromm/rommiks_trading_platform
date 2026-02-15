"""Monitor ByBit for new spot listings."""

from __future__ import annotations

from sqlalchemy import select

from src.collector.exchange import ExchangeClient
from src.core.database import async_session
from src.core.logger import get_logger
from src.core.models import Symbol

log = get_logger("screener.listings")


async def check_new_listings() -> list[dict]:
    """Compare current ByBit spot pairs with DB symbols.

    Returns list of newly discovered pairs (not yet in DB).
    """
    client = ExchangeClient()
    new_pairs: list[dict] = []

    try:
        await client.connect()
        markets = await client.fetch_markets()

        # Filter USDT spot pairs
        spot_symbols = {
            m["id"]: {"base": m["base"], "quote": m["quote"]}
            for m in markets
            if m.get("spot") and m.get("quote") == "USDT" and m.get("active")
        }

        # Get known symbols from DB
        async with async_session() as session:
            result = await session.execute(select(Symbol.name))
            known = {row[0] for row in result.all()}

        # Find new ones
        for symbol_name, info in spot_symbols.items():
            if symbol_name not in known:
                new_pairs.append({
                    "symbol": symbol_name,
                    "base": info["base"],
                    "quote": info["quote"],
                })

        if new_pairs:
            log.info("new_listings_found", count=len(new_pairs), pairs=new_pairs)
        else:
            log.debug("no_new_listings")

    finally:
        await client.close()

    return new_pairs
