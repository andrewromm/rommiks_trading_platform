"""Symbol discovery and management for ByBit USDT spot pairs."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.collector.exchange import ExchangeClient
from src.core.logger import get_logger
from src.core.models import Symbol

log = get_logger("collector.symbols")

# Minimum 24h volume in USD to include a pair
DEFAULT_MIN_VOLUME_USD = 1_000_000


async def fetch_usdt_spot_pairs(client: ExchangeClient) -> list[dict]:
    """Fetch all active USDT spot pairs from ByBit."""
    markets = await client.fetch_markets()
    pairs = [
        m
        for m in markets
        if m.get("spot")
        and m.get("active")
        and m.get("quote") == "USDT"
        and m.get("symbol", "").endswith("/USDT")
    ]
    log.info("fetched_usdt_pairs", count=len(pairs))
    return pairs


async def get_top_symbols_by_volume(
    client: ExchangeClient,
    pairs: list[dict],
    top_n: int = 50,
    min_volume_usd: float = DEFAULT_MIN_VOLUME_USD,
) -> list[dict]:
    """Filter pairs by 24h volume and return top N."""
    symbols = [p["symbol"] for p in pairs]
    tickers = await client.fetch_tickers(symbols)

    ranked = []
    for pair in pairs:
        ticker = tickers.get(pair["symbol"])
        if not ticker:
            continue
        vol_usd = ticker.get("quoteVolume") or 0
        if vol_usd >= min_volume_usd:
            ranked.append({**pair, "volume_24h_usd": vol_usd})

    ranked.sort(key=lambda x: x["volume_24h_usd"], reverse=True)
    result = ranked[:top_n]
    log.info(
        "top_symbols_by_volume",
        total_above_min=len(ranked),
        selected=len(result),
        min_volume=min_volume_usd,
    )
    return result


async def sync_symbols_to_db(session: AsyncSession, pairs: list[dict]) -> int:
    """Upsert symbols into the database. Returns count of upserted rows."""
    if not pairs:
        return 0

    values = []
    for p in pairs:
        # ccxt symbol format: "BTC/USDT" → db name: "BTCUSDT"
        name = p["symbol"].replace("/", "")
        values.append(
            {
                "name": name,
                "base": p.get("base", ""),
                "quote": p.get("quote", ""),
                "is_active": True,
                "price_precision": p.get("precision", {}).get("price"),
                "qty_precision": p.get("precision", {}).get("amount"),
            }
        )

    stmt = pg_insert(Symbol).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["name"],
        set_={
            "base": stmt.excluded.base,
            "quote": stmt.excluded.quote,
            "is_active": stmt.excluded.is_active,
            "price_precision": stmt.excluded.price_precision,
            "qty_precision": stmt.excluded.qty_precision,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    log.info("symbols_synced", count=len(values))
    return result.rowcount


async def get_active_symbols(session: AsyncSession) -> list[str]:
    """Get list of active symbol names from DB (e.g. ['BTCUSDT', 'ETHUSDT'])."""
    result = await session.execute(
        select(Symbol.name).where(Symbol.is_active.is_(True)).order_by(Symbol.name)
    )
    return list(result.scalars().all())
