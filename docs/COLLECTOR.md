# M1: Market Data Collector

Модуль сбора рыночных данных с биржи ByBit. Обеспечивает историческую загрузку OHLCV-свечей и real-time стриминг тикеров.

## Архитектура

```
ByBit REST API ──► ExchangeClient ──► OHLCV backfill ──► TimescaleDB
                       │
                       ├──► Symbol discovery ──► PostgreSQL (symbols)
                       │
ByBit WebSocket ──► WebSocketManager ──► Redis (ticker cache)
```

### Компоненты

| Файл | Назначение |
|------|-----------|
| `exchange.py` | Async-обёртка над ccxt для ByBit API |
| `symbols.py` | Обнаружение USDT-пар, фильтрация по объёму, синхронизация с БД |
| `storage.py` | Batch upsert OHLCV в TimescaleDB, запросы по свечам |
| `ohlcv.py` | Инкрементальный бэкфилл исторических данных |
| `websocket.py` | WebSocket-менеджер для real-time тикеров |
| `cli.py` | CLI-команды (backfill, stream, status) |
| `__main__.py` | Entry point для `python -m src.collector` |

---

## CLI-команды

Все команды доступны через `python -m src.collector <command>` или через Makefile внутри Docker.

### backfill — загрузка исторических данных

```bash
# Одна пара, один таймфрейм
make collector-backfill         # или внутри контейнера:
python -m src.collector backfill --symbol BTCUSDT --timeframe 1h --days 30

# Все таймфреймы для одной пары
python -m src.collector backfill --symbol ETHUSDT --days 90

# Автоматически: топ-50 по объёму, все таймфреймы
python -m src.collector backfill --days 90 --top 50
```

**Параметры:**

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--symbol` | *(пусто = все)* | Символ (BTCUSDT). Пусто — автообнаружение топ-N |
| `--timeframe` | *(пусто = все)* | Таймфрейм (5m, 15m, 1h, 4h, 1d). Пусто — все |
| `--days` | 90 | Глубина истории в днях |
| `--top` | 50 | Количество топ-пар по объёму (если --symbol не указан) |

**Как работает:**
1. Если `--symbol` не указан — запрашивает ByBit API, находит все USDT spot пары, сортирует по 24h объёму, берёт топ-N
2. Для каждой пары и таймфрейма проверяет последнюю свечу в БД
3. Загружает данные от последней свечи (или от `now - days`) до текущего момента
4. Пакетами по 200 свечей (лимит ByBit API)
5. Upsert в БД (ON CONFLICT DO UPDATE) — нет дубликатов при повторном запуске
6. При ошибке API — 3 попытки с exponential backoff (1s, 2s, 4s)

### stream — real-time тикеры

```bash
make collector-stream           # или:
python -m src.collector stream --top 50
```

**Параметры:**

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--top` | 50 | Количество пар для стриминга |

**Как работает:**
1. Запрашивает топ-N пар по объёму через REST API
2. Открывает WebSocket соединение к ByBit v5 public API
3. Подписывается на тикеры (батчами по 10 — лимит ByBit)
4. Каждое обновление тикера сохраняется в Redis hash с TTL 60s
5. При обрыве — автоматический reconnect с exponential backoff (5s → 60s)
6. Graceful shutdown по SIGINT/SIGTERM

**Формат данных в Redis:**

```
Key: ticker:BTCUSDT
Type: Hash
Fields:
  symbol:       "BTCUSDT"
  last_price:   "97500.50"
  price_24h_pct: "0.0234"
  high_24h:     "98100.00"
  low_24h:      "95200.00"
  volume_24h:   "12345.67"
  turnover_24h: "1203456789.00"
  updated_at:   "2026-02-15T09:30:00.123456+00:00"
TTL: 60 seconds
```

### status — состояние данных

```bash
make collector-status           # или:
python -m src.collector status
```

Выводит таблицу: символ, таймфрейм, количество свечей, первая/последняя дата.

---

## Хранение данных

### OHLCV (TimescaleDB hypertable)

```
Таблица: ohlcv
PK: (symbol, timeframe, timestamp) — композитный
Chunk interval: 7 дней
Индексы: ix_ohlcv_symbol, ix_ohlcv_timestamp
```

Формат данных:
- `symbol` — VARCHAR(20), например `BTCUSDT`
- `timeframe` — VARCHAR(5): `5m`, `15m`, `1h`, `4h`, `1d`
- `timestamp` — TIMESTAMPTZ, начало свечи
- `open`, `high`, `low`, `close`, `volume` — DOUBLE PRECISION

Upsert: при повторной загрузке данные обновляются (OHLCV может меняться для незакрытых свечей).

### Symbols (PostgreSQL)

```
Таблица: symbols
PK: id (serial)
Unique: name
```

Хранит метаданные торговых пар: base/quote, precision, is_active.
Обновляется при каждом запуске `backfill` без `--symbol`.

### Ticker cache (Redis)

Hash `ticker:{SYMBOL}` с TTL 60s. Если WebSocket не обновляет данные — ключ автоматически удаляется.

---

## Таймфреймы

| Таймфрейм | Интервал | Свечей за 90 дней | Применение |
|-----------|----------|-------------------|-----------|
| 5m | 5 минут | ~25,920 | Скальпинг, точные входы |
| 15m | 15 минут | ~8,640 | Внутридневная торговля |
| 1h | 1 час | ~2,160 | Основной рабочий ТФ |
| 4h | 4 часа | ~540 | Среднесрок, тренд |
| 1d | 1 день | ~90 | Общая картина, тренд |

---

## Обработка ошибок

| Ситуация | Поведение |
|----------|----------|
| Ошибка API при backfill | 3 попытки, exponential backoff (1s → 2s → 4s), затем переход к следующему символу |
| InvalidNonce (рассинхрон часов) | Автоматический retry через ccxt |
| WebSocket обрыв | Reconnect с backoff (5s → 10s → 20s → 40s → 60s max) |
| WebSocket subscribe fail | Лог warning, продолжение работы |
| Дубликаты данных | ON CONFLICT DO UPDATE — идемпотентно |
| Неполная свеча (null OHLC) | Пропускается при save |

---

## Конфигурация

Через `.env` (см. `.env.example`):

| Переменная | Описание |
|-----------|----------|
| `BYBIT_API_KEY` | API key (read-only) |
| `BYBIT_API_SECRET` | API secret |
| `BYBIT_TESTNET` | `true` для testnet |
| `POSTGRES_*` | Подключение к БД |
| `REDIS_HOST`, `REDIS_PORT` | Подключение к Redis |

**Testnet vs Mainnet:**
- `BYBIT_TESTNET=true` → `wss://stream-testnet.bybit.com/v5/public/spot`
- `BYBIT_TESTNET=false` → `wss://stream.bybit.com/v5/public/spot`

---

## Зависимости

- `ccxt` — async клиент биржи
- `websockets` — WebSocket соединение
- `asyncpg` — async PostgreSQL драйвер
- `psycopg2-binary` — sync PostgreSQL драйвер (для Alembic миграций)
- `redis[hiredis]` — async Redis клиент
- `typer` — CLI framework

---

## Миграции

Две Alembic-миграции создают схему для коллектора:

1. `1e3eb60714a3_initial_schema.py` — все 6 таблиц (ohlcv, symbols, signals, sentiment_data, whale_transactions, paper_trades)
2. `0002_ohlcv_hypertable.py` — конвертация ohlcv в TimescaleDB hypertable

Применение:
```bash
make db-upgrade   # или: docker compose exec app alembic upgrade head
```

---

## Что ещё не реализовано

- [ ] Retention policy для 5m свечей (удаление старше 1 месяца)
- [ ] Heartbeat-лог каждые 5 минут в stream режиме
- [ ] Метрики задержки и пропусков данных
- [ ] Подписка на kline (свечи) через WebSocket (сейчас только тикеры)
- [ ] 24-часовой тест стабильности WebSocket на VPS
