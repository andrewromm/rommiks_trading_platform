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
docker compose up -d --build

# Проверить что всё поднялось
docker compose ps

# Применить миграции БД
docker compose exec app alembic upgrade head

# Посмотреть логи
docker compose logs -f app
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

## 3. Остановка и перезапуск

### Остановить всё

```bash
docker compose down
```

### Остановить с сохранением данных

```bash
docker compose down
# Данные PostgreSQL и Redis сохраняются в /srv/rommiks/data/
```

### Остановить и УДАЛИТЬ данные (осторожно!)

```bash
docker compose down
sudo rm -rf /srv/rommiks/data/postgres/* /srv/rommiks/data/redis/*
# ВСЕ данные БД будут потеряны!
```

### Перезапуск приложения (без перезапуска БД)

```bash
docker compose restart app
```

### Перезапуск с пересборкой (после обновления кода)

```bash
docker compose up -d --build app
```

### Полный перезапуск всего стека

```bash
docker compose down && docker compose up -d
```

---

## 4. Обновление кода

```bash
cd /srv/rommiks/trading

# Забрать обновления
git pull origin main

# Пересобрать и перезапустить приложение
docker compose up -d --build app

# Применить новые миграции (если есть)
docker compose exec app alembic upgrade head
```

---

## 5. Логи

### Все логи в реальном времени

```bash
docker compose logs -f
```

### Логи конкретного сервиса

```bash
docker compose logs -f app      # приложение
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

## 6. Мониторинг

### Состояние контейнеров

```bash
docker compose ps
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

## 7. Работа с базой данных

### Подключение к PostgreSQL

```bash
docker compose exec db psql -U trading
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
docker compose exec app alembic upgrade head

# Откатить последнюю миграцию
docker compose exec app alembic downgrade -1

# Посмотреть текущую ревизию
docker compose exec app alembic current

# Посмотреть историю миграций
docker compose exec app alembic history
```

---

## 8. Автозапуск при перезагрузке VPS

Docker с `restart: unless-stopped` перезапустит контейнеры автоматически при перезагрузке сервера. Убедитесь, что Docker включён в автозапуск:

```bash
sudo systemctl enable docker
```

Проверка после перезагрузки:

```bash
sudo reboot
# ... подождать ~1 минуту, переподключиться
docker compose ps
```

---

## 9. Обновление Docker-образов

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

## 10. Troubleshooting

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

## 11. Безопасность: чеклист

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

## 12. Регулярное обслуживание

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
echo "=== Containers ===" && docker compose ps && \
echo "=== Resources ===" && docker stats --no-stream && \
echo "=== Disk ===" && df -h / && \
echo "=== Memory ===" && free -h
```
