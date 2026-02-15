# Trading System — Project Context

## What is this project
AI-powered crypto trading recommendation system for ByBit exchange. Generates trading signals based on technical analysis, sentiment, on-chain data, and prediction markets. Delivers signals via Telegram and console dashboard. Does NOT execute trades automatically (recommendation only).

## Current status
M0 (Foundation) complete. Working on M1 (Market Data Collector).

## Architecture

```
src/
├── core/         # Config, logger, database, Redis, ORM models
├── collector/    # M1: ByBit market data collection (ccxt, WebSocket)
├── analyzer/     # M2: Technical analysis engine
├── screener/     # M3: Coin screener and ranking
├── sentiment/    # M4: News and social sentiment (LLM-powered)
├── onchain/      # M5: Whale tracking, exchange flows, Polymarket
├── scoring/      # M6: Multi-factor signal scoring
├── delivery/     # Telegram bot, notifications
├── dashboard/    # M7: Console TUI dashboard (Textual)
└── backtest/     # Backtesting and paper trading
```

## Tech stack
- **Python 3.12**, async (asyncio + uvloop)
- **SQLAlchemy 2.0** async with asyncpg
- **PostgreSQL 16 + TimescaleDB** for time-series data
- **Redis 7** for caching and queues
- **ccxt** for exchange API (ByBit)
- **structlog** for logging (JSON in prod, console in dev)
- **pydantic-settings** for configuration
- **Docker Compose** for deployment

## Key commands
```bash
# Run tests
source .venv/bin/activate && pytest tests/ -v

# Lint
ruff check src/ tests/

# Docker
docker compose up -d --build
docker compose logs -f app
docker compose exec app alembic upgrade head

# Alembic migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Important conventions
- All communication in Russian (user is Russian-speaking)
- All code, comments, and git messages in English
- Use `Numeric(20, 8)` for price fields (Signal, PaperTrade, WhaleTransaction)
- Use `Float` for OHLCV data (performance over precision)
- All `DateTime` columns must have `timezone=True`
- API keys are **read-only** — no trade execution permissions
- OpenClaw runs on a SEPARATE VPS — never co-locate with trading system
- Tables are created ONLY via Alembic migrations, not `create_all`

## Configuration
All config via `.env` file (see `.env.example`). Loaded by `src/core/config.py` using pydantic-settings.

## Database models (src/core/models.py)
- `Symbol` — trading pair metadata
- `OHLCV` — candlestick data (TimescaleDB hypertable)
- `Signal` — generated trading signals with entry/SL/TP
- `SentimentData` — sentiment scores from various sources
- `WhaleTransaction` — large on-chain transactions
- `PaperTrade` — simulated trades for testing (FK to Signal)

## Deployment
- VPS: 4 CPU, 8GB RAM (Hetzner or similar)
- Docker Compose with memory limits: db=3G, redis=512M, app=2G
- Ports bound to 127.0.0.1 only (not exposed externally)
- See `docs/VPS_OPERATIONS.md` for full deployment guide

## Documentation
- `ANALYSIS.md` — market research, risk analysis, realistic return expectations
- `PLAN.md` — 8-week implementation roadmap (M0–M7)
- `docs/VPS_OPERATIONS.md` — deployment, monitoring, troubleshooting

## Security rules
- Never commit `.env` or API keys
- ByBit API keys: read-only only
- OpenClaw: never give access to exchange API keys
- PostgreSQL/Redis: listen on 127.0.0.1 only
- All secrets via environment variables
