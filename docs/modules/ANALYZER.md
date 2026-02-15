# M2: Technical Analysis Engine

Модуль технического анализа. Вычисляет индикаторы, определяет уровни поддержки/сопротивления, генерирует торговые сигналы с confidence-скорингом, stop-loss, take-profit и расчётом позиции.

## Архитектура

```
OHLCV (TimescaleDB)
  │
  ├──► compute_indicators()    19 индикаторов (EMA, MACD, RSI, BB, ATR, ...)
  │         │
  │         ├──► find_support_resistance()   уровни S/R через swing high/low
  │         │
  │         ├──► compute_htf_trend()         тренд старшего ТФ (MTF)
  │         │
  │         └──► generate_signals()          оценка long/short
  │                   │
  │                   ├──► compute_sl_tp()           SL/TP с учётом S/R
  │                   ├──► compute_position_size()   размер позиции по риску
  │                   └──► SignalCandidate
  │
  └──► save_signal() ──► PostgreSQL (signals)
```

### Компоненты

| Файл | Назначение |
|------|-----------|
| `indicators.py` | Вычисление 19 технических индикаторов на OHLCV DataFrame |
| `levels.py` | Определение S/R через swing high/low + кластеризация |
| `signals.py` | Правила генерации сигналов, confidence-скоринг, SL/TP, позиция |
| `mtf.py` | Multi-timeframe анализ — тренд старшего таймфрейма |
| `engine.py` | Оркестратор: загрузка данных, расчёт, сохранение сигналов |
| `cli.py` | CLI-команды (analyze, scan, signals) |
| `__main__.py` | Entry point для `python -m src.analyzer` |

---

## Индикаторы (indicators.py)

Функция `compute_indicators(df)` добавляет 19 колонок к OHLCV DataFrame. Не мутирует входные данные — возвращает копию.

### Тренд

| Индикатор | Колонка | Параметры |
|-----------|---------|-----------|
| EMA | `ema_9`, `ema_21`, `ema_50`, `ema_200` | Периоды 9, 21, 50, 200 |
| MACD | `macd`, `macd_signal`, `macd_hist` | Fast=12, Slow=26, Signal=9 |

### Моментум

| Индикатор | Колонка | Параметры |
|-----------|---------|-----------|
| RSI | `rsi_14` | Период 14 |
| Stochastic RSI | `stochrsi_k`, `stochrsi_d` | Период 14, Smooth K=3, D=3 |

### Волатильность

| Индикатор | Колонка | Параметры |
|-----------|---------|-----------|
| Bollinger Bands | `bb_upper`, `bb_middle`, `bb_lower` | Период 20, StdDev=2 |
| ATR | `atr_14` | Период 14 |

### Объём

| Индикатор | Колонка | Параметры |
|-----------|---------|-----------|
| OBV | `obv` | — |
| Volume SMA | `vol_sma_20` | Период 20 |
| VWAP | `vwap` | Кумулятивный |

### Производные

| Индикатор | Колонка | Логика |
|-----------|---------|--------|
| EMA Trend | `ema_trend` | 1 если EMA21 > EMA50, -1 если <, 0 если = |
| Volume Ratio | `vol_ratio` | volume / vol_sma_20 |

---

## Уровни поддержки/сопротивления (levels.py)

### Алгоритм

1. **Swing Highs/Lows** — скользящее окно (2 * window + 1), ищет локальные экстремумы
2. **Кластеризация** — близкие уровни (в пределах `tolerance_pct` %) группируются в один
3. **Сортировка** — по количеству касаний (touches), топ `max_levels`

### Параметры

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `window` | 5 | Размер окна для swing detection (11 свечей) |
| `tolerance_pct` | 0.5 | Процент для кластеризации (0.5% от цены) |
| `max_levels` | 10 | Максимум уровней каждого типа |

### Использование в SL

Если ближайший уровень S/R находится ближе к entry, чем ATR-based SL, стоп-лосс размещается за этим уровнем с буфером ATR/4.

---

## Генерация сигналов (signals.py)

### Процесс оценки

Анализируется только последняя (самая свежая) свеча. Приоритет: сначала проверяется long, если не проходит — short.

### Обязательные условия

**Long:**
- `ema_trend == 1` (EMA21 > EMA50)
- Цена > EMA200 (если EMA200 доступна)

**Short:**
- `ema_trend == -1` (EMA21 < EMA50)
- Цена < EMA200 (если EMA200 доступна)

### Confidence-скоринг

Базовый confidence: **0.50** (при прохождении обязательных условий).

| Фактор | Long | Short | Бонус |
|--------|------|-------|-------|
| RSI pullback | RSI 30–50 | RSI 50–70 | +0.10 |
| RSI extreme | RSI > 70 | RSI < 30 | -0.10 |
| MACD bullish/bearish | hist > 0 | hist < 0 | +0.10 |
| MACD crossover | hist пересёк 0 снизу | hist пересёк 0 сверху | +0.10 |
| Volume above avg | vol_ratio > 1.0 | vol_ratio > 1.0 | +0.10 |
| BB position | Цена < BB middle | Цена > BB middle | +0.05 |
| StochRSI | K > D | K < D | +0.05 |
| HTF aligned | HTF trend = 1 | HTF trend = -1 | +0.10 |
| HTF conflict | HTF trend = -1 | HTF trend = 1 | -0.15 |

**Итоговый диапазон:** [0.00, 0.90]

**Минимальный порог для сигнала:** `MIN_CONFIDENCE = 0.55`

### Stop-Loss и Take-Profit

**SL (compute_sl_tp):**
- Базовый: `entry ± ATR * 1.5`
- Если ближайший S/R уровень ближе → SL за S/R с буфером `ATR * 0.25`
- Формула: `sl = nearest_sr ∓ buffer`

**TP (три уровня):**

| Уровень | R:R | Формула |
|---------|-----|---------|
| TP1 | 1.5 | entry ± risk * 1.5 |
| TP2 | 2.5 | entry ± risk * 2.5 |
| TP3 | 4.0 | entry ± risk * 4.0 |

### Размер позиции (compute_position_size)

Формула: `position_size = (risk_pct / risk_per_unit) * 100`

Где:
- `risk_pct` = 0.02 (2% капитала по умолчанию)
- `risk_per_unit` = |entry - sl| / entry

**Ограничение:** максимум 20% капитала на одну позицию.

---

## Multi-Timeframe анализ (mtf.py)

### Маппинг таймфреймов

| Рабочий ТФ | Старший ТФ |
|------------|-----------|
| 5m | 1h |
| 15m | 4h |
| 1h | 4h |
| 4h | 1d |
| 1d | *(нет)* |

### Определение тренда старшего ТФ

На старшем ТФ вычисляются индикаторы, затем проверяется:

| Условие | Результат |
|---------|-----------|
| EMA21 > EMA50 **и** close > EMA200 | Bullish (+1) |
| EMA21 < EMA50 **и** close < EMA200 | Bearish (-1) |
| Иначе | Neutral (0) |

Минимум свечей для старшего ТФ: **210** (для расчёта EMA200).

---

## Оркестратор (engine.py)

### Пайплайн analyze_symbol

```
1. Check cooldown (4h)  ──► если активен → пропуск
2. Load OHLCV (мин. 210 свечей)
3. Load HTF OHLCV (если есть старший ТФ)
   ── одна DB-сессия для всех read-операций ──
4. compute_indicators()
5. find_support_resistance()
6. compute_htf_trend()
7. generate_signals()
   ── CPU-фаза, без DB ──
8. save_signal() для каждого кандидата
   ── одна DB-сессия для write ──
```

### Ключевые параметры

| Параметр | Значение | Описание |
|----------|---------|----------|
| `MIN_CANDLES` | 210 | Минимум свечей для анализа |
| `SIGNAL_COOLDOWN_HOURS` | 4 | Кулдаун между сигналами одного символа/ТФ |
| `ENTRY_TIMEFRAMES` | 15m, 1h, 4h | Таймфреймы для генерации сигналов |

### Expiry сигналов

| Таймфрейм | Срок действия |
|-----------|--------------|
| 5m | 1 час |
| 15m | 4 часа |
| 1h | 12 часов |
| 4h | 48 часов |
| 1d | 168 часов (7 дней) |

---

## CLI-команды

Все команды через `python -m src.analyzer <command>` или Makefile.

### analyze — анализ одного символа

```bash
make analyzer-run symbol=BTCUSDT timeframe=1h
# или внутри контейнера:
python -m src.analyzer analyze --symbol BTCUSDT --timeframe 1h
```

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--symbol` | BTCUSDT | Символ для анализа |
| `--timeframe` | 1h | Таймфрейм (15m, 1h, 4h) |

**Вывод:**
```
SIGNAL: LONG BTCUSDT @ 70735.20 | SL=69788.30 TP1=72155.55 | confidence=65% R:R=1.5
```

### scan — массовый скан

```bash
make analyzer-scan top=50
# или:
python -m src.analyzer scan --top 50 --timeframe 1h
```

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--top` | 50 | Количество топ-символов |
| `--timeframe` | *(пусто = все)* | Один ТФ. Пусто = все entry TFs (15m, 1h, 4h) |

### signals — просмотр сигналов

```bash
make analyzer-signals limit=20
# или:
python -m src.analyzer signals --symbol BTCUSDT --limit 20
```

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--symbol` | *(пусто = все)* | Фильтр по символу |
| `--limit` | 20 | Количество последних сигналов |

**Вывод:**
```
   ID Symbol       Dir    TF     Conf         Entry  Status     Created
-------------------------------------------------------------------------------------
    2 ETHUSDT      LONG   1h     70%  2124.56000000  new        2026-02-15 13:28
    1 BTCUSDT      LONG   1h     65%  70735.20000000  new        2026-02-15 13:28
```

---

## Хранение сигналов

### Таблица signals (PostgreSQL)

```
PK: id (serial)
Поля:
  symbol          VARCHAR(20)
  direction       ENUM (long, short)
  timeframe       VARCHAR(5)
  confidence      FLOAT           — 0.00–0.90
  entry_price     NUMERIC(20,8)
  stop_loss       NUMERIC(20,8)
  take_profit_1   NUMERIC(20,8)
  take_profit_2   NUMERIC(20,8)   — nullable
  take_profit_3   NUMERIC(20,8)   — nullable
  risk_reward     FLOAT
  position_size_pct FLOAT
  source          VARCHAR(50)     — "technical_analysis"
  status          ENUM (new, active, closed, expired, cancelled)
  indicators      JSONB           — снапшот всех индикаторов + levels + reasons
  created_at      TIMESTAMPTZ
  expires_at      TIMESTAMPTZ
  closed_at       TIMESTAMPTZ     — nullable
```

### Структура indicators (JSONB)

```json
{
  "ema_9": 70248.01,
  "ema_21": 70146.06,
  "ema_50": 69926.98,
  "macd": 37.03,
  "macd_signal": -101.18,
  "macd_hist": 138.21,
  "rsi_14": 52.34,
  "stochrsi_k": 0.68,
  "stochrsi_d": 0.55,
  "bb_upper": 72100.50,
  "bb_middle": 70200.30,
  "bb_lower": 68300.10,
  "atr_14": 631.80,
  "vol_ratio": 1.10,
  "levels": {
    "support": [{"price": 69500.0, "touches": 3}],
    "resistance": [{"price": 72200.0, "touches": 2}]
  },
  "reasons": ["ema_21 > ema_50", "macd_bullish", "stochrsi_bullish"]
}
```

---

## Тесты

23 unit-теста в `tests/unit/test_analyzer.py`:

| Группа | Тестов | Что проверяется |
|--------|--------|----------------|
| TestIndicators | 5 | Все колонки, длина, иммутабельность, ema_trend, RSI bounds |
| TestLevels | 6 | Swing highs/lows, кластеризация, S/R, nearest support/resistance |
| TestSignals | 10 | SL/TP long/short/with S/R, позиция, evaluate long/short, generate_signals |
| TestMTF | 2 | Маппинг ТФ, наличие HTF для всех entry ТФ |

Запуск:
```bash
make test
# или:
poetry run pytest tests/unit/test_analyzer.py -v
```

---

## Зависимости

- `ta` — библиотека технических индикаторов
- `pandas` — DataFrames для OHLCV и индикаторов
- `numpy` — числовые операции
- `sqlalchemy[asyncio]` + `asyncpg` — async DB
- `typer` — CLI framework

---

## Что ещё не реализовано

- [ ] Candlestick pattern recognition (doji, hammer, engulfing)
- [ ] Divergence detection (RSI/MACD divergences)
- [ ] Dynamic confidence weights (на основе backtesting)
- [ ] Объединение сигналов с нескольких ТФ (multi-timeframe confluence)
- [ ] Telegram-уведомления при генерации сигнала
- [ ] Scheduler для автоматического запуска анализа (cron / APScheduler)
