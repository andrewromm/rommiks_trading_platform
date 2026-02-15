# Операции на VPS: запуск, управление, обслуживание

## Структура каталогов на VPS

```
/srv/rommiks/
├── trading/          # git-репозиторий проекта
├── data/
│   ├── postgres/     # данные PostgreSQL (bind mount)
│   └── redis/        # данные Redis (bind mount)
├── backups/          # бэкапы БД (.sql.gz)
└── logs/             # логи приложения
```

---

## 1. Первоначальная настройка VPS

### Требования
- Ubuntu 22.04+ или Debian 12+
- 2 vCPU, 4GB RAM, 40GB+ SSD
- Docker + Docker Compose

### Установка Docker

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Перелогиниться для применения группы
exit
# ... заново подключиться по SSH

# Проверка
docker --version
docker compose version
```

### Настройка firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
# НЕ открываем порты PostgreSQL и Redis наружу — они слушают только 127.0.0.1
sudo ufw enable
```

### Автоматическая настройка (рекомендуется)

```bash
# Одна команда — скачает и запустит bootstrap-скрипт
curl -fsSL https://raw.githubusercontent.com/andrewromm/rommiks_trading_platform/main/scripts/bootstrap.sh \
  | sudo bash -s -- https://github.com/andrewromm/rommiks_trading_platform.git
```

Скрипт автоматически:
- Установит Docker и зависимости
- Создаст структуру `/srv/rommiks/`
- Клонирует репозиторий
- Сгенерирует `.env` с паролем PostgreSQL
- Настроит firewall и swap
- Добавит cron для ежедневных бэкапов

### Ручная настройка

```bash
# Клонирование
git clone <REPO_URL> /srv/rommiks/trading
cd /srv/rommiks/trading
```

### Настройка окружения

```bash
cp .env.example .env
nano .env
```

Обязательно заменить:
- `POSTGRES_PASSWORD` — сильный пароль (генерировать: `openssl rand -base64 24`)
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` — ключи ByBit (read-only!)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
- `LLM_API_KEY`

```bash
# Защитить файл
chmod 600 .env
```

---

## 2. Запуск

### Первый запуск

```bash
cd /srv/rommiks/trading

# Собрать образы и поднять всё
make up
# или с пересборкой: make build

# Проверить что всё поднялось
make ps

# Применить миграции БД
make db-upgrade

# Посмотреть логи
make logs
```

### Ожидаемый вывод при старте

```
db      | ... database system is ready to accept connections
redis   | * Ready to accept connections
app     | starting_trading_system environment=development testnet=true
app     | database_connected
app     | redis_connected
app     | system_ready
```

---

## 3. Makefile — справочник команд

Все основные операции доступны через `make`. Выполнять из директории проекта (`/srv/rommiks/trading`).

```bash
make help    # Показать список всех доступных команд
```

### Разработка

| Команда | Описание |
|---|---|
| `make setup` | Установить все зависимости через Poetry |
| `make test` | Запустить тесты |
| `make lint` | Проверить код линтером (ruff) |
| `make fmt` | Автоформатирование кода |
| `make check` | Lint + тесты вместе |
| `make lock` | Обновить poetry.lock |

### Docker

| Команда | Описание |
|---|---|
| `make up` | Запустить все контейнеры |
| `make down` | Остановить все контейнеры |
| `make build` | Пересобрать и перезапустить app |
| `make restart` | Перезапустить app (без пересборки) |
| `make ps` | Статус контейнеров |
| `make logs` | Логи app в реальном времени |
| `make logs-all` | Логи всех сервисов |

### База данных

| Команда | Описание |
|---|---|
| `make db-upgrade` | Применить все миграции |
| `make db-downgrade` | Откатить последнюю миграцию |
| `make db-migrate msg="описание"` | Создать новую миграцию |
| `make db-history` | История миграций |
| `make db-current` | Текущая ревизия миграции |
| `make db-shell` | Открыть psql-консоль |
| `make db-backup` | Создать бэкап в `/srv/rommiks/backups/` |
| `make db-restore file=путь` | Восстановить из бэкапа |

### Redis

| Команда | Описание |
|---|---|
| `make redis-shell` | Открыть redis-cli |

### Деплой и мониторинг

| Команда | Описание |
|---|---|
| `make deploy` | Pull + пересборка + миграции |
| `make status` | Полная диагностика системы |
| `make clean` | Очистить кэши Python |
| `make clean-docker` | Очистить неиспользуемые Docker-образы |

### Типовые сценарии

```bash
# Первый запуск на VPS
make up && make db-upgrade

# Обновление после git pull
make deploy

# Быстрая проверка что всё работает
make status

# Ежедневный бэкап (также настроен в cron)
make db-backup
```

---

## 4. Остановка и перезапуск

### Остановить всё

```bash
make down
```

### Остановить с сохранением данных

```bash
make down
# Данные PostgreSQL и Redis сохраняются в /srv/rommiks/data/
```

### Остановить и УДАЛИТЬ данные (осторожно!)

```bash
make down
sudo rm -rf /srv/rommiks/data/postgres/* /srv/rommiks/data/redis/*
# ВСЕ данные БД будут потеряны!
```

### Перезапуск приложения (без перезапуска БД)

```bash
make restart
```

### Перезапуск с пересборкой (после обновления кода)

```bash
make build
```

### Полный перезапуск всего стека

```bash
make down && make up
```

---

## 5. Обновление кода

```bash
cd /srv/rommiks/trading

# Всё в одну команду: pull + rebuild + migrate
make deploy

# Или вручную по шагам:
git pull origin main
make build
make db-upgrade
```

---

## 6. Логи

### Все логи в реальном времени

```bash
make logs-all
```

### Логи приложения

```bash
make logs
```

### Логи конкретного сервиса (db, redis)

```bash
docker compose logs -f db       # PostgreSQL
docker compose logs -f redis    # Redis
```

### Последние N строк

```bash
docker compose logs --tail=100 app
```

### Логи с таймстампами

```bash
docker compose logs -f -t app
```

---

## 7. Мониторинг

### Полная диагностика

```bash
make status
```

Выводит: контейнеры, ресурсы, диск, размер БД.

### Состояние контейнеров

```bash
make ps
```

Ожидаемый вывод — все сервисы `Up (healthy)`:
```
NAME      STATUS              PORTS
db        Up (healthy)        127.0.0.1:5432->5432/tcp
redis     Up (healthy)        127.0.0.1:6379->6379/tcp
app       Up
```

### Потребление ресурсов

```bash
docker stats --no-stream
```

### Проверка healthcheck вручную

```bash
# PostgreSQL
docker compose exec db pg_isready -U trading

# Redis
docker compose exec redis redis-cli ping
```

### Размер данных БД

```bash
docker compose exec db psql -U trading -c "
  SELECT pg_size_pretty(pg_database_size('trading')) AS db_size;
"
```

### Размер данных

```bash
du -sh /srv/rommiks/data/postgres /srv/rommiks/data/redis /srv/rommiks/backups
```

---

## 8. Работа с базой данных

### Подключение к PostgreSQL

```bash
make db-shell
```

### Полезные SQL-запросы

```sql
-- Количество свечей по символам
SELECT symbol, timeframe, COUNT(*) as cnt
FROM ohlcv
GROUP BY symbol, timeframe
ORDER BY symbol, timeframe;

-- Последние сигналы
SELECT symbol, direction, confidence, created_at
FROM signals
ORDER BY created_at DESC
LIMIT 20;

-- Статистика paper trading
SELECT
  COUNT(*) as total_trades,
  COUNT(*) FILTER (WHERE pnl > 0) as wins,
  COUNT(*) FILTER (WHERE pnl <= 0) as losses,
  ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl_pct,
  ROUND(SUM(pnl)::numeric, 2) as total_pnl
FROM paper_trades
WHERE closed_at IS NOT NULL;
```

### Бэкап БД

```bash
# Создать бэкап (через Makefile)
make db-backup
# Бэкапы сохраняются в /srv/rommiks/backups/

# Или вручную
docker compose exec db pg_dump -U trading trading | gzip > /srv/rommiks/backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Восстановить из бэкапа
make db-restore file=/srv/rommiks/backups/backup_20260215.sql.gz
```

### Миграции

```bash
# Применить все миграции
make db-upgrade

# Откатить последнюю миграцию
make db-downgrade

# Посмотреть текущую ревизию
make db-current

# Посмотреть историю миграций
make db-history
```

---

## 9. Автозапуск при перезагрузке VPS

Docker с `restart: unless-stopped` перезапустит контейнеры автоматически при перезагрузке сервера. Убедитесь, что Docker включён в автозапуск:

```bash
sudo systemctl enable docker
```

Проверка после перезагрузки:

```bash
sudo reboot
# ... подождать ~1 минуту, переподключиться
cd /srv/rommiks/trading && make status
```

---

## 10. Обновление Docker-образов

### Обновить базовые образы (PostgreSQL, Redis)

```bash
docker compose pull
docker compose up -d
```

### Очистка старых образов

```bash
# Удалить неиспользуемые образы
docker image prune -f

# Полная очистка (образы, кэш сборки)
docker system prune -f
```

---

## 11. Troubleshooting

### Контейнер не запускается

```bash
# Подробные логи
docker compose logs app

# Проверить конфигурацию
docker compose config

# Запустить в foreground для отладки
docker compose up app
```

### БД не подключается

```bash
# Проверить что контейнер БД работает
docker compose ps db

# Проверить логи БД
docker compose logs db

# Проверить доступность изнутри app
docker compose exec app python -c "
from src.core.config import settings
print(settings.database_url)
"
```

### Redis не отвечает

```bash
docker compose exec redis redis-cli ping
docker compose logs redis
```

### Нехватка места на диске

```bash
# Проверить диск
df -h

# Очистить Docker (старые образы и кэш сборки)
docker system prune -f
```

### Нехватка памяти

```bash
# Текущее потребление
free -h
docker stats --no-stream

# Если OOM — увеличить swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Перезапуск зависшего контейнера

```bash
docker compose restart app
# или жёстко:
docker compose kill app && docker compose up -d app
```

---

## 12. Безопасность: чеклист

- [ ] `.env` имеет права `600` (`chmod 600 .env`)
- [ ] `.env` **НЕ** в git (проверить: `git status`)
- [ ] API-ключи ByBit — **только read-only** (без прав на торговлю)
- [ ] PostgreSQL и Redis слушают только `127.0.0.1`, не `0.0.0.0`
- [ ] UFW включён, открыт только SSH
- [ ] SSH по ключам, пароль отключён
- [ ] Регулярные бэкапы БД

### Проверка что порты не торчат наружу

```bash
sudo ss -tlnp | grep -E '5432|6379'
# Должно быть 127.0.0.1:5432 и 127.0.0.1:6379, НЕ 0.0.0.0
```

---

## 13. Регулярное обслуживание

### Еженедельно
- Проверить логи на ошибки: `docker compose logs --since 7d app | grep -i error`
- Проверить размер БД
- Проверить `docker stats` на потребление ресурсов

### Ежемесячно
- Бэкап БД
- `docker system prune -f` — очистка старых образов
- `sudo apt update && sudo apt upgrade -y` — обновление системы
- Обновить базовые Docker-образы (`docker compose pull`)

### Команда быстрой диагностики

```bash
make status
```
