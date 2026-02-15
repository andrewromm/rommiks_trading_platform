# План реализации: AI Trading Recommendation System

**Дата:** 2026-02-15
**Горизонт:** 8 недель (2 месяца) → готовность к большим тестам
**Принцип:** модуль в неделю, каждый тестируется на стабильность 7 дней

---

## Обзор модулей

```
Неделя   Модуль                         Зависит от    Paper Trading
──────   ──────                         ──────────    ─────────────
  1      M0: Фундамент                  —             —
  2      M1: Market Data Collector       M0            —
  3      M2: Technical Analysis          M1            —
  4      M3: Delivery + Screener         M1, M2        Старт (ручной)
  5      M4: Sentiment & News            M0            Продолжается
  6      M5: On-chain + Polymarket       M0            Продолжается
  7      M6: Multi-factor Scoring        M2, M4, M5    Авто paper trading
  8      M7: Dashboard + Финализация     Все           Полный цикл
──────
  9+     БОЛЬШИЕ ТЕСТЫ (2–4 недели paper trading с полной системой)
```

### Граф зависимостей

```
M0 (Фундамент)
 ├── M1 (Market Data)
 │    ├── M2 (Tech Analysis)
 │    │    └── M3 (Delivery + Screener)
 │    │         └── M6 (Scoring) ←── M4, M5
 │    │              └── M7 (Dashboard)
 ├── M4 (Sentiment)  ──────────────┘
 └── M5 (On-chain)   ──────────────┘
```

---

## Структура проекта

```
trading/
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── alembic/                # Миграции БД
├── src/
│   ├── core/               # Конфиг, логгер, БД, базовые модели
│   ├── collector/          # M1: сбор рыночных данных
│   ├── analyzer/           # M2: технический анализ
│   ├── screener/           # M3: скринер монет
│   ├── sentiment/          # M4: сентимент и новости
│   ├── onchain/            # M5: on-chain и Polymarket
│   ├── scoring/            # M6: мультифакторный скоринг
│   ├── delivery/           # Telegram bot, уведомления
│   ├── dashboard/          # M7: консольный дашборд (Textual)
│   └── backtest/           # Бэктестинг и paper trading
├── tests/
│   ├── unit/
│   └── integration/
├── n8n/                    # Экспорт n8n workflow (JSON)
└── docs/
```

---

## M0: Фундамент (Неделя 1)

### Цель
Рабочее окружение, инфраструктура, деплой на VPS. После этой недели — скелет проекта готов к разработке модулей.

### Задачи

- [x] **Инициализация проекта**
  - Python 3.11+, Poetry
  - Структура директорий (см. выше)
  - Линтинг (ruff), типизация (mypy)
  - `.env.example` с описанием переменных

- [x] **Docker-инфраструктура**
  - `docker-compose.yml`: PostgreSQL 16 + TimescaleDB, Redis 7, приложение
  - Dockerfile для Python-приложения
  - Bind mounts для персистентных данных (`/srv/rommiks/data/`)
  - Healthcheck для каждого сервиса

- [x] **База данных**
  - Alembic для миграций
  - Базовые модели: `Symbol`, `OHLCV`, `Signal`, `SentimentData`, `WhaleTransaction`, `PaperTrade`
  - TimescaleDB hypertable для OHLCV (chunk interval 7 дней)
  - Индексы для частых запросов

- [x] **Core-модуль**
  - Конфигурация через pydantic-settings
  - Логирование (structlog)
  - Базовый async-каркас (asyncio + uvloop)
  - Обработка ошибок и graceful shutdown

- [x] **Деплой**
  - VPS: bootstrap-скрипт (`scripts/bootstrap.sh`)
  - Bind mounts, memory limits, 127.0.0.1 only
  - Makefile с командами управления
  - Документация: `docs/VPS_OPERATIONS.md`

- [x] **Безопасность**
  - Secrets в `.env` (не в коде, не в git)
  - `.gitignore` для чувствительных файлов
  - API-ключи ByBit: **только read-only** на этом этапе

### Критерии приёмки
- [x] `docker-compose up` поднимает все сервисы без ошибок
- [x] PostgreSQL + TimescaleDB доступна, миграции проходят
- [x] Redis доступен
- [ ] Проект запускается на VPS *(VPS ещё не развёрнут)*
- [x] Логи пишутся структурированно
- [x] Тесты проходят (`pytest` — 13 тестов)

---

## M1: Market Data Collector (Неделя 2)

### Цель
Непрерывный сбор рыночных данных с ByBit. К концу недели — 7 дней стабильной работы.

### Задачи

- [x] **REST API — историческая загрузка**
  - Подключение к ByBit через ccxt (async)
  - Загрузка OHLCV: таймфреймы 5m, 15m, 1h, 4h, 1d
  - Backfill с инкрементальным обновлением (до 3 месяцев)
  - Rate limiting через ccxt (enableRateLimit)
  - Список символов: все USDT-пары на ByBit spot (фильтр по объёму)

- [x] **WebSocket — real-time данные**
  - Подписка на ticker (цена, объём 24h) для топ-N пар
  - Auto-reconnect с exponential backoff (5s → 60s)
  - Heartbeat через websockets ping_interval
  - Graceful shutdown через signal handlers (SIGINT/SIGTERM)

- [x] **Хранение**
  - OHLCV → TimescaleDB hypertable (chunk interval 7 дней)
  - Ticker данные → Redis hash с TTL 60s (atomic pipeline)
  - Дедупликация через ON CONFLICT DO UPDATE
  - [ ] Retention policy: 5m свечи — 1 месяц, 1h+ — без лимита *(не реализовано)*

- [ ] **Мониторинг коллектора**
  - [ ] Heartbeat: лог каждые 5 минут с количеством обработанных записей
  - [x] Лог при потере и восстановлении WebSocket соединения
  - [ ] Метрики: задержка данных, количество пропусков

- [x] **CLI-команды**
  - `python -m src.collector backfill --symbol BTCUSDT --days 90`
  - `python -m src.collector stream --top 50`
  - `python -m src.collector status`

### Критерии приёмки
- [x] Исторические данные загружаются корректно (проверено: BTCUSDT, ETHUSDT)
- [ ] WebSocket работает 24 часа без потерь данных *(требуется тест на VPS)*
- [ ] Задержка real-time данных < 2 секунды
- [x] Автоматический reconnect с exponential backoff
- [x] Данные в БД консистентны (upsert, инкрементальный бэкфилл без дубликатов)

---

## M2: Technical Analysis Engine (Неделя 3)

### Цель
Расчёт индикаторов и генерация базовых торговых сигналов по ТА.

### Задачи

- [ ] **Индикаторы (на каждом таймфрейме)**
  - Трендовые: EMA(9, 21, 50, 200), MACD(12, 26, 9)
  - Осцилляторы: RSI(14), Stochastic RSI
  - Волатильность: Bollinger Bands(20, 2), ATR(14)
  - Объём: OBV, Volume SMA(20), VWAP
  - Поддержка/сопротивление: авто-определение по swing high/low

- [ ] **Мультитаймфрейм анализ**
  - Определение тренда на 4h и 1d (EMA crossover, structure)
  - Поиск точек входа на 15m и 1h (в направлении тренда)
  - Конфликт таймфреймов → снижение confidence

- [ ] **Генерация сигналов ТА**
  - Тип: LONG / SHORT / NEUTRAL
  - Confidence: 0–100%
  - Вход (entry), стоп-лосс (SL), тейк-профит (TP 1, TP 2, TP 3)
  - Risk/Reward ratio
  - Рекомендуемый размер позиции (% от капитала, на основе ATR)

- [ ] **Модель данных сигнала**
  ```
  Signal:
    symbol: str           # "BTCUSDT"
    direction: enum       # LONG / SHORT / NEUTRAL
    timeframe: str        # "1h"
    confidence: float     # 0.0–1.0
    entry_price: float
    stop_loss: float
    take_profit: [float]  # TP1, TP2, TP3
    risk_reward: float
    position_size_pct: float
    indicators: dict      # Snapshot индикаторов
    source: str           # "technical_analysis"
    created_at: datetime
    expires_at: datetime
  ```

- [ ] **Валидация**
  - Сравнение сигналов с TradingView на 5–10 монетах
  - Бэктест сигналов на исторических данных (3 месяца)
  - Расчёт: win rate, avg R:R, profit factor

### Критерии приёмки
- [ ] Индикаторы совпадают с TradingView (допуск <1%)
- [ ] Сигналы генерируются автоматически при срабатывании условий
- [ ] Бэктест на 3 месяцах показывает win rate >50%
- [ ] Сигнал содержит entry, SL, TP, confidence
- [ ] Работает на всех топ-50 парах параллельно

---

## M3: Delivery + Screener (Неделя 4)

### Цель
Телеграм-сигналы и ежедневный скринер монет. **Начало ручного paper trading.**

### Задачи

- [ ] **Telegram Bot**
  - Форматированные сигналы (entry, SL, TP, confidence, R:R)
  - Команды:
    - `/status` — состояние системы, uptime, последний сигнал
    - `/top N` — топ-N монет по скору
    - `/signal BTCUSDT` — текущий анализ монеты
    - `/portfolio` — обзор paper portfolio (позже)
    - `/settings` — настройка фильтров (мин. confidence, монеты)
  - Режимы уведомлений: все сигналы / только сильные (confidence >70%)
  - Форматирование: Markdown, цветовые метки (зелёный/красный)

- [ ] **Скринер монет**
  - Ежедневный запуск: анализ всех USDT-пар на ByBit
  - Фильтры:
    - Минимальный объём 24h (>$1M)
    - Минимальная ликвидность (спред <0.5%)
  - Ранжирование по: сила тренда, объём, волатильность, RSI setup
  - Вывод: топ-10 монет для торговли сегодня

- [ ] **Мониторинг новых листингов**
  - Проверка ByBit API на новые пары каждые 15 минут
  - Алерт в Telegram при новом листинге
  - Базовая информация: символ, начальная цена, объём

- [ ] **n8n интеграция**
  - Workflow: сильный сигнал → Telegram уведомление
  - Workflow: ежедневный дайджест (утро) → топ монеты + обзор рынка
  - Workflow: новый листинг → алерт

- [ ] **Paper Trading (ручной)**
  - Таблица в БД: paper_trades (entry, exit, P&L)
  - Telegram команда: `/trade BTCUSDT long 100` — записать сделку
  - `/close BTCUSDT 67500` — закрыть сделку, рассчитать P&L
  - Ежедневная сводка: open trades, P&L

### Критерии приёмки
- [ ] Telegram бот отвечает на все команды < 3 секунд
- [ ] Сигналы приходят в Telegram в течение 30 секунд после генерации
- [ ] Ежедневный скринер выдаёт топ-10 с обоснованием
- [ ] Алерт на новый листинг < 5 минут после появления
- [ ] Paper trading: могу записывать и отслеживать сделки
- [ ] **Начат ручной paper trading по сигналам системы**

---

## M4: Sentiment & News (Неделя 5)

### Цель
AI-анализ настроений рынка. Sentiment score интегрирован в сигналы.

### Задачи

- [ ] **Источники данных**
  - **Fear & Greed Index** — alternative.me API (бесплатно)
  - **LunarCrush** — social metrics (бесплатный tier или API)
  - **CoinGecko** — trending coins, community data
  - **RSS/News** — CoinDesk, CoinTelegraph, Decrypt (через n8n)
  - **Reddit** — r/cryptocurrency, r/bitcoin (PRAW, бесплатно)
  - **Альтернатива Twitter/X**: агрегаторы или OpenClaw для парсинга

- [ ] **Sentiment Analysis**
  - LLM-based анализ новостей (классификация: bullish/bearish/neutral)
  - Привязка новости к конкретной монете
  - Sentiment score: -1.0 (extreme fear) — +1.0 (extreme greed)
  - Исторический sentiment (хранение в БД, тренд)

- [ ] **OpenClaw интеграция**
  - Задача: "проанализируй последние новости о {symbol}"
  - Результат: структурированный JSON с sentiment и ключевыми факторами
  - Периодичность: каждые 2–4 часа для топ-20 монет
  - **Безопасность**: OpenClaw НЕ получает API-ключи бирж

- [ ] **n8n workflow**
  - Сбор новостей из RSS каждый час
  - Отправка на анализ LLM
  - Сохранение результата в БД
  - Алерт при резком изменении sentiment

- [ ] **Модель данных**
  ```
  SentimentData:
    symbol: str
    source: str           # "lunarcrush", "news", "reddit", "fear_greed"
    score: float          # -1.0 to 1.0
    volume: int           # количество упоминаний
    summary: str          # краткое резюме от LLM
    raw_data: dict
    created_at: datetime
  ```

### Критерии приёмки
- [ ] Fear & Greed Index обновляется ежедневно
- [ ] Sentiment score для топ-20 монет обновляется каждые 2–4 часа
- [ ] LLM-анализ новостей корректно классифицирует sentiment (проверка на 50 новостях)
- [ ] Алерт при резком развороте sentiment (delta >0.3 за 4 часа)
- [ ] Данные сохраняются в БД с историей

---

## M5: On-chain + Polymarket (Неделя 6)

### Цель
Мониторинг китов, exchange flows и предсказательных рынков.

### Задачи

- [ ] **Whale Tracking**
  - Whale Alert API (бесплатный tier: 10 req/min)
  - Фильтр: транзакции >$1M для BTC/ETH, >$500K для альтов
  - Классификация: exchange inflow (медвежий), outflow (бычий), transfer
  - Алерт в Telegram при крупных движениях
  - Хранение в БД с агрегацией (net flow за час/день)

- [ ] **Exchange Flows (бесплатные источники)**
  - CryptoQuant free tier (ограниченные метрики)
  - Dune Analytics: пользовательские SQL-запросы (exchange wallets)
  - Метрики: net exchange flow, stablecoin inflow (buying power)
  - Обновление: каждые 1–4 часа

- [ ] **Polymarket**
  - API: получение рынков связанных с крипто (BTC price targets, ETF, regulation)
  - Трекинг вероятностей ключевых событий
  - Алерт при значительном изменении вероятности (delta >10%)
  - Контекст для макро-анализа (не прямой торговый сигнал)

- [ ] **Модели данных**
  ```
  WhaleTransaction:
    tx_hash: str
    symbol: str
    amount_usd: float
    from_type: str        # "exchange", "whale", "unknown"
    to_type: str
    direction: str        # "inflow", "outflow", "transfer"
    created_at: datetime

  PolymarketEvent:
    market_id: str
    title: str
    probability: float
    volume: float
    related_symbols: [str]
    updated_at: datetime
  ```

- [ ] **Агрегация**
  - Hourly net flow по exchange (для BTC, ETH)
  - Daily whale activity score
  - Polymarket sentiment по крипто-темам

### Критерии приёмки
- [ ] Whale Alert данные поступают в real-time
- [ ] Алерт в Telegram при транзакциях >$10M < 5 минут
- [ ] Exchange flow net data обновляется каждые 4 часа
- [ ] Polymarket данные по 5+ крипто-рынкам обновляются каждый час
- [ ] Все данные сохраняются в БД с историей

---

## M6: Multi-factor Scoring System (Неделя 7)

### Цель
Объединение всех источников сигналов в единый скор. Бэктестинг.

### Задачи

- [ ] **Мультифакторная модель**
  - Веса (начальные, подлежат калибровке):
    ```
    Technical Analysis:  40%   (M2)
    Sentiment:           20%   (M4)
    On-chain:            20%   (M5)
    Market Context:      10%   (Polymarket, Fear&Greed)
    Momentum:            10%   (объём, цена за 24h/7d)
    ```
  - Итоговый скор: 0–100 (>70 = сильный сигнал, <30 = избегать)
  - Consensus: сигнал только когда 3+ источника согласны

- [ ] **Risk Scoring**
  - ATR-based volatility assessment
  - Position sizing рекомендация (% от капитала)
  - Risk/Reward enforcement (минимум 1:2)
  - Max concurrent positions (рекомендация: 3–5 при $1000)
  - Max allocation per trade (рекомендация: 10–20% капитала)

- [ ] **Фильтрация ложных сигналов**
  - Минимальный confidence threshold (настраиваемый, дефолт 65%)
  - Cooldown: не более 1 сигнала на пару за 4 часа
  - Блокировка сигналов при аномальной волатильности (ATR > 3x нормы)
  - Блокировка при отрицательном sentiment + бычьем TA (конфликт)

- [ ] **Бэктестинг**
  - Прогон модели на исторических данных (3 месяца)
  - Метрики: win rate, profit factor, max drawdown, Sharpe ratio
  - Оптимизация весов (grid search, без overfitting — walk-forward)
  - Сравнение: мультифактор vs только TA

- [ ] **Auto Paper Trading**
  - Автоматическая запись сделок по сигналам (paper mode)
  - Виртуальный портфель: $1000 начальный капитал
  - Автоматический стоп-лосс и тейк-профит
  - Ежедневный отчёт: P&L, win rate, open positions

### Критерии приёмки
- [ ] Единый скор генерируется для каждой монеты каждые 15 минут
- [ ] Бэктест на 3 месяцах: profit factor > 1.3, max drawdown < 20%
- [ ] Auto paper trading работает 24/7 без ошибок
- [ ] Ложные сигналы сокращены на 30%+ по сравнению с чистым TA
- [ ] Risk scoring корректно ограничивает размер позиций

---

## M7: Dashboard + Финализация (Неделя 8)

### Цель
Консольный дашборд, финальная интеграция, подготовка к большим тестам.

### Задачи

- [ ] **Консольный дашборд (Textual)**
  - **Экран 1: Market Overview**
    - Топ-20 монет: цена, изменение 24h, объём, тренд
    - Fear & Greed Index
    - BTC dominance
    - Общий sentiment рынка
  - **Экран 2: Active Signals**
    - Текущие сигналы: символ, направление, confidence, скор, entry/SL/TP
    - Статус: new / active / expired / hit_tp / hit_sl
    - Фильтры: по монете, по confidence, по направлению
  - **Экран 3: Paper Portfolio**
    - Open positions: entry, current price, unrealized P&L
    - Closed positions: P&L, win/loss
    - Метрики: total P&L, win rate, avg R:R, max drawdown
  - **Экран 4: Data Status**
    - Статус каждого data source (last update, errors)
    - WebSocket status
    - Системные метрики (CPU, RAM, DB size)

- [ ] **Финальная интеграция**
  - Все модули работают вместе в едином docker-compose
  - Graceful startup/shutdown порядок
  - Error recovery: автоматический перезапуск упавших модулей
  - Единый лог-поток с фильтрацией по модулю

- [ ] **Performance Tracking**
  - Автоматический расчёт: win rate, profit factor, Sharpe, max drawdown
  - Сравнение с benchmark (BTC buy & hold)
  - Еженедельный отчёт в Telegram
  - Экспорт в CSV для внешнего анализа

- [ ] **Документация**
  - README: установка, конфигурация, запуск
  - Описание каждого модуля
  - FAQ: частые проблемы и решения
  - Руководство по интерпретации сигналов (для новичка)

- [ ] **Стабилизация**
  - Нагрузочное тестирование: все модули одновременно, 48 часов
  - Исправление обнаруженных багов
  - Оптимизация потребления ресурсов (RAM, CPU на VPS)

### Критерии приёмки
- [ ] Дашборд запускается и отображает все 4 экрана без ошибок
- [ ] Обновление данных в дашборде < 5 секунд
- [ ] Все модули стабильно работают 48 часов подряд
- [ ] Auto paper trading работает корректно
- [ ] Документация покрывает установку и использование
- [ ] **Система готова к большим тестам**

---

## Большие тесты (Неделя 9–12)

### Что это
2–4 недели полностью автоматического paper trading с работающей системой. Цель — проверить систему в реальных рыночных условиях без риска потери денег.

### Метрики успеха

| Метрика | Целевое значение | Критический минимум |
|---------|-----------------|---------------------|
| Win Rate | >55% | >45% |
| Profit Factor | >1.5 | >1.2 |
| Max Drawdown | <10% | <20% |
| Sharpe Ratio | >1.5 | >1.0 |
| System Uptime | >99% | >95% |
| Signal Latency | <30 сек | <60 сек |
| Signals per Day | 3–10 | >1 |
| vs BTC Buy&Hold | Outperform | — |

### Процесс
1. Запуск полной системы в paper trading режиме
2. Ежедневный мониторинг через дашборд + Telegram
3. Еженедельный анализ метрик
4. Корректировка весов и параметров при необходимости
5. По итогам — решение о переходе на реальную торговлю

### Критерии перехода к реальной торговле
- [ ] 4 недели стабильной работы (uptime >99%)
- [ ] Profit factor >1.3 за весь период
- [ ] Max drawdown <15%
- [ ] Не менее 50 завершённых paper trades
- [ ] Понимание пользователем всех сигналов и рисков

---

## Буфер и приоритеты

### Если не укладываемся в неделю
Модули по приоритету сокращения scope:
1. **M7 Dashboard** — можно упростить до минимального (1 экран вместо 4)
2. **M5 Polymarket** — можно отложить, on-chain оставить
3. **M4 OpenClaw интеграция** — можно заменить на простой RSS + LLM API

### Что нельзя сокращать
- M0 (Фундамент) — без него ничего не работает
- M1 (Data) — основа всей системы
- M2 (TA) — основной источник сигналов
- M3 (Telegram) — без доставки система бесполезна
- M6 (Scoring) — без скоринга это не "AI система", а набор индикаторов

---

## Бюджет на сервисы (ежемесячный)

| Сервис | Стоимость | Необходимость |
|--------|----------|---------------|
| VPS (2 CPU, 4GB RAM) | $5–15 | Обязательно |
| ByBit API | Бесплатно | Обязательно |
| Whale Alert API | Бесплатно (10 req/min) | Обязательно |
| LunarCrush / Santiment | $0–30 | Желательно |
| CoinGecko API | Бесплатно (free tier) | Обязательно |
| Fear & Greed API | Бесплатно | Обязательно |
| LLM API (Claude/GPT) | $5–20 | Обязательно (для sentiment) |
| Polymarket API | Бесплатно | Желательно |
| Dune Analytics | Бесплатно | Желательно |
| **Итого** | **$10–65/мес** | |

---

## Следующий шаг

→ Формирование **детального ТЗ для M0 (Фундамент)** и начало реализации.
