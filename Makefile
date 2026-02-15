.PHONY: help setup test lint fmt check up down build logs restart ps \
       db-migrate db-upgrade db-downgrade db-shell db-backup \
       redis-shell deploy status clean lock

SHELL := /bin/bash
APP_CONTAINER := app
DB_CONTAINER := db
REDIS_CONTAINER := redis
BACKUP_DIR := /srv/rommiks/backups

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Development ──────────────────────────────────────────────

setup: ## Install all dependencies via Poetry
	poetry install --with dev
	@echo "Done. Run: poetry shell"

test: ## Run tests
	poetry run pytest tests/ -v

lint: ## Run linter
	poetry run ruff check src/ tests/

fmt: ## Format code
	poetry run ruff check src/ tests/ --fix
	poetry run ruff format src/ tests/

check: lint test ## Run lint + tests

lock: ## Update poetry.lock
	poetry lock
	@echo "poetry.lock updated"

# ─── Docker ───────────────────────────────────────────────────

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Rebuild and restart app
	docker compose up -d --build $(APP_CONTAINER)

logs: ## Follow app logs
	docker compose logs -f $(APP_CONTAINER)

logs-all: ## Follow all logs
	docker compose logs -f

restart: ## Restart app container
	docker compose restart $(APP_CONTAINER)

ps: ## Show container status
	docker compose ps

# ─── Database ─────────────────────────────────────────────────

db-migrate: ## Create migration (usage: make db-migrate msg="add new table")
	docker compose exec $(APP_CONTAINER) alembic revision --autogenerate -m "$(msg)"

db-upgrade: ## Apply all pending migrations
	docker compose exec $(APP_CONTAINER) alembic upgrade head

db-downgrade: ## Rollback last migration
	docker compose exec $(APP_CONTAINER) alembic downgrade -1

db-history: ## Show migration history
	docker compose exec $(APP_CONTAINER) alembic history

db-current: ## Show current migration revision
	docker compose exec $(APP_CONTAINER) alembic current

db-shell: ## Open psql shell
	docker compose exec $(DB_CONTAINER) psql -U trading

db-backup: ## Create database backup
	@mkdir -p $(BACKUP_DIR)
	docker compose exec $(DB_CONTAINER) pg_dump -U trading trading | \
		gzip > $(BACKUP_DIR)/backup_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "Backup saved to $(BACKUP_DIR)/"

db-restore: ## Restore from backup (usage: make db-restore file=backups/backup_xxx.sql.gz)
	gunzip -c $(file) | docker compose exec -T $(DB_CONTAINER) psql -U trading trading

# ─── Redis ────────────────────────────────────────────────────

redis-shell: ## Open redis-cli
	docker compose exec $(REDIS_CONTAINER) redis-cli

# ─── Deploy ───────────────────────────────────────────────────

deploy: ## Pull latest code, rebuild, migrate
	git pull origin main
	docker compose up -d --build $(APP_CONTAINER)
	docker compose exec $(APP_CONTAINER) alembic upgrade head
	@echo "Deploy complete"

# ─── Monitoring ───────────────────────────────────────────────

status: ## Full system diagnostics
	@echo "=== Containers ==="
	@docker compose ps
	@echo ""
	@echo "=== Resources ==="
	@docker stats --no-stream $$(docker compose ps -q) 2>/dev/null || true
	@echo ""
	@echo "=== Disk ==="
	@df -h / 2>/dev/null | head -2
	@echo ""
	@echo "=== DB Size ==="
	@docker compose exec $(DB_CONTAINER) psql -U trading -t -c \
		"SELECT pg_size_pretty(pg_database_size('trading'));" 2>/dev/null || echo "DB not running"

# ─── Cleanup ──────────────────────────────────────────────────

clean: ## Remove caches and compiled files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage

clean-docker: ## Remove unused Docker images and build cache
	docker system prune -f
