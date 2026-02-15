# Trading System — Project Context

## What is this project
AI-powered crypto trading recommendation system for ByBit exchange. Generates trading signals based on technical analysis, sentiment, on-chain data, and prediction markets. Delivers signals via Telegram and console dashboard. Does NOT execute trades automatically (recommendation only).

## Current status
M0 (Foundation) and M1 (Market Data Collector) complete. Migrations applied, backfill tested. Next: M2 (Technical Analysis).

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

## Key commands (via Makefile)
```bash
make help              # Show all commands
make setup             # Install deps via Poetry
make check             # Lint + tests
make test              # Tests only
make lint              # Lint only
make fmt               # Auto-format code
make lock              # Update poetry.lock

make up                # Start Docker services
make down              # Stop Docker services
make build             # Rebuild app container
make logs              # Follow app logs
make ps                # Container status
make status            # Full system diagnostics

make db-upgrade        # Apply migrations
make db-migrate msg="description"  # Create migration
make db-downgrade      # Rollback last migration
make db-shell          # Open psql
make db-backup         # Backup database

make deploy            # Pull + rebuild + migrate
make clean             # Remove caches
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
- Base directory: `/srv/rommiks/` (trading/, data/, backups/, logs/)
- Data stored via bind mounts, NOT Docker named volumes
- Bootstrap: `sudo bash scripts/bootstrap.sh <REPO_URL>`
- Docker Compose with memory limits: db=3G, redis=512M, app=2G
- Ports bound to 127.0.0.1 only (not exposed externally)
- See `docs/VPS_OPERATIONS.md` for full deployment guide

## Documentation
- `docs/ANALYSIS.md` — market research, risk analysis, realistic return expectations
- `docs/PLAN.md` — 8-week implementation roadmap (M0–M7)
- `docs/COLLECTOR.md` — M1 collector module: architecture, CLI, data format
- `docs/VPS_OPERATIONS.md` — deployment, monitoring, troubleshooting

## Security rules
- Never commit `.env` or API keys
- ByBit API keys: read-only only
- OpenClaw: never give access to exchange API keys
- PostgreSQL/Redis: listen on 127.0.0.1 only
- All secrets via environment variables
