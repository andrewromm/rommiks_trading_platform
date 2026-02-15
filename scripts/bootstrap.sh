#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────
BASE_DIR="/srv/rommiks"
REPO_URL="${1:-}"
APP_USER="${USER}"

# ─── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ─── Pre-checks ──────────────────────────────────────────────
echo ""
echo "=== Rommiks Trading System — Bootstrap ==="
echo "Base directory: ${BASE_DIR}"
echo "User: ${APP_USER}"
echo ""

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo ./bootstrap.sh)"
fi

# ─── 1. System packages ──────────────────────────────────────
log "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

log "Installing prerequisites..."
apt-get install -y -qq \
    curl \
    git \
    make \
    ufw \
    htop \
    > /dev/null

# ─── 2. Docker ────────────────────────────────────────────────
if command -v docker &> /dev/null; then
    log "Docker already installed: $(docker --version)"
else
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    log "Docker installed: $(docker --version)"
fi

# Add user to docker group
if ! groups "${APP_USER}" | grep -q docker; then
    usermod -aG docker "${APP_USER}"
    log "Added ${APP_USER} to docker group (re-login required)"
fi

# Enable Docker on boot
systemctl enable docker
systemctl start docker

# ─── 3. Directory structure ───────────────────────────────────
log "Creating directory structure..."

mkdir -p "${BASE_DIR}/trading"
mkdir -p "${BASE_DIR}/data/postgres"
mkdir -p "${BASE_DIR}/data/redis"
mkdir -p "${BASE_DIR}/backups"
mkdir -p "${BASE_DIR}/logs"

# Set ownership
chown -R "${APP_USER}:${APP_USER}" "${BASE_DIR}"

# PostgreSQL needs specific ownership (will be managed by Docker container UID 999)
chown -R 999:999 "${BASE_DIR}/data/postgres"

log "Directory structure created:"
echo "    ${BASE_DIR}/"
echo "    ├── trading/          # git repository"
echo "    ├── data/"
echo "    │   ├── postgres/     # PostgreSQL data"
echo "    │   └── redis/        # Redis data"
echo "    ├── backups/          # database backups"
echo "    └── logs/             # application logs"

# ─── 4. Clone repository ─────────────────────────────────────
if [[ -n "${REPO_URL}" ]]; then
    if [[ -d "${BASE_DIR}/trading/.git" ]]; then
        warn "Repository already cloned, pulling latest..."
        cd "${BASE_DIR}/trading"
        sudo -u "${APP_USER}" git pull
    else
        log "Cloning repository..."
        sudo -u "${APP_USER}" git clone "${REPO_URL}" "${BASE_DIR}/trading"
    fi
    log "Repository ready"
else
    warn "No repository URL provided. Clone manually:"
    echo "    git clone <REPO_URL> ${BASE_DIR}/trading"
fi

# ─── 5. Environment file ─────────────────────────────────────
if [[ -f "${BASE_DIR}/trading/.env" ]]; then
    warn ".env already exists, skipping"
else
    if [[ -f "${BASE_DIR}/trading/.env.example" ]]; then
        cp "${BASE_DIR}/trading/.env.example" "${BASE_DIR}/trading/.env"
        # Generate a random password for PostgreSQL
        PG_PASS=$(openssl rand -base64 24)
        sed -i "s/CHANGE_ME_strong_password_here/${PG_PASS}/" "${BASE_DIR}/trading/.env"
        chmod 600 "${BASE_DIR}/trading/.env"
        chown "${APP_USER}:${APP_USER}" "${BASE_DIR}/trading/.env"
        log ".env created with generated PostgreSQL password"
        warn "Edit .env to add API keys: nano ${BASE_DIR}/trading/.env"
    else
        warn ".env.example not found. Create .env manually after cloning."
    fi
fi

# ─── 6. Firewall ──────────────────────────────────────────────
log "Configuring firewall..."
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow ssh > /dev/null 2>&1
echo "y" | ufw enable > /dev/null 2>&1
log "Firewall enabled (SSH only)"

# ─── 7. Swap (if not exists) ──────────────────────────────────
if [[ ! -f /swapfile ]]; then
    log "Creating 2GB swap..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile > /dev/null
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log "Swap enabled"
else
    log "Swap already exists"
fi

# ─── 8. Cron for backups ──────────────────────────────────────
CRON_JOB="0 3 * * * cd ${BASE_DIR}/trading && make db-backup >> ${BASE_DIR}/logs/backup.log 2>&1"
if ! crontab -u "${APP_USER}" -l 2>/dev/null | grep -q "db-backup"; then
    (crontab -u "${APP_USER}" -l 2>/dev/null; echo "${CRON_JOB}") | crontab -u "${APP_USER}" -
    log "Daily backup cron added (03:00)"
else
    log "Backup cron already exists"
fi

# ─── Done ─────────────────────────────────────────────────────
echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Re-login to apply docker group: exit && ssh ..."
echo "  2. Edit .env:          nano ${BASE_DIR}/trading/.env"
echo "  3. Start services:     cd ${BASE_DIR}/trading && make up"
echo "  4. Run migrations:     make db-upgrade"
echo "  5. Check status:       make status"
echo ""
