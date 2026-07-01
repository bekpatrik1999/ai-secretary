#!/usr/bin/env bash
# =============================================================================
# AI Secretary — one-shot bootstrap for Ubuntu 22.04 LTS
# Target host  : secr-app-d01  (172.16.7.215)
# Specs        : 16 vCPU / 32 GB RAM / 350 GB SSD
# Run as root  : sudo bash deploy/install.sh
# =============================================================================
set -euo pipefail

APP_USER="aisec"
APP_DIR="/opt/ai-secretary"
PY_VER="python3.10"   # ships by default with Ubuntu 22.04
OLLAMA_MODEL_DEFAULT="qwen2.5:7b"

log() { printf "\n\033[1;36m[install]\033[0m %s\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Run me with sudo (need root for apt, useradd, systemd)." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Base system
# ---------------------------------------------------------------------------
log "Updating apt and installing OS dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg lsb-release \
  build-essential pkg-config git unzip \
  python3.10 python3.10-venv python3.10-dev python3-pip \
  ffmpeg libpq-dev \
  nginx \
  ufw

# ---------------------------------------------------------------------------
# 2. Hostname
# ---------------------------------------------------------------------------
log "Setting hostname to secr-app-d01..."
hostnamectl set-hostname secr-app-d01
if ! grep -q "172.16.7.215\s\+secr-app-d01" /etc/hosts; then
  echo "172.16.7.215   secr-app-d01" >> /etc/hosts
fi

# ---------------------------------------------------------------------------
# 3. Docker Engine + Compose plugin (official Docker repo)
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  log "Docker already installed — skipping."
fi

# ---------------------------------------------------------------------------
# 4. Ollama (native install, CPU mode)
# ---------------------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  log "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  systemctl enable --now ollama
else
  log "Ollama already installed — skipping."
fi

# ---------------------------------------------------------------------------
# 5. Service user
# ---------------------------------------------------------------------------
if ! id "${APP_USER}" >/dev/null 2>&1; then
  log "Creating system user ${APP_USER}..."
  useradd --system --create-home --shell /usr/sbin/nologin --home-dir /home/${APP_USER} ${APP_USER}
fi
usermod -aG docker ${APP_USER}

# ---------------------------------------------------------------------------
# 6. App directory + Python venv
# ---------------------------------------------------------------------------
log "Provisioning ${APP_DIR}..."
mkdir -p "${APP_DIR}"
# Sync the current repo into /opt/ai-secretary (this script lives in deploy/).
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${SRC_DIR}" != "${APP_DIR}" ]]; then
  rsync -a --delete \
    --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
    --exclude='.DS_Store' --exclude='.claude' \
    "${SRC_DIR}/" "${APP_DIR}/"
fi
chown -R ${APP_USER}:${APP_USER} "${APP_DIR}"

log "Creating Python venv..."
sudo -u ${APP_USER} ${PY_VER} -m venv "${APP_DIR}/.venv"
sudo -u ${APP_USER} "${APP_DIR}/.venv/bin/pip" install --upgrade pip wheel
sudo -u ${APP_USER} "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# ---------------------------------------------------------------------------
# 7. .env — keep operator's edits; create from example only if missing
# ---------------------------------------------------------------------------
if [[ ! -f "${APP_DIR}/.env" ]]; then
  log "Seeding .env from .env.example — EDIT THE SECRETS BEFORE STARTING."
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi

# ---------------------------------------------------------------------------
# 8. Bring up Postgres + MinIO, run migrations
# ---------------------------------------------------------------------------
log "Starting Postgres and MinIO containers..."
sudo -u ${APP_USER} docker compose -f "${APP_DIR}/docker-compose.yml" --env-file "${APP_DIR}/.env" up -d

log "Waiting for Postgres to become healthy..."
for i in {1..60}; do
  if sudo -u ${APP_USER} docker exec aisec_postgres pg_isready -U "$(grep ^POSTGRES_USER ${APP_DIR}/.env | cut -d= -f2)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

log "Running Alembic migrations..."
sudo -u ${APP_USER} bash -c "set -a; source ${APP_DIR}/.env; set +a; ${APP_DIR}/.venv/bin/alembic -c ${APP_DIR}/alembic.ini upgrade head"

# ---------------------------------------------------------------------------
# 9. Pull Ollama model
# ---------------------------------------------------------------------------
OLLAMA_MODEL="$(grep ^OLLAMA_MODEL "${APP_DIR}/.env" | cut -d= -f2 || true)"
OLLAMA_MODEL="${OLLAMA_MODEL:-${OLLAMA_MODEL_DEFAULT}}"
log "Pulling Ollama model: ${OLLAMA_MODEL} (this can take several minutes)..."
ollama pull "${OLLAMA_MODEL}"

# ---------------------------------------------------------------------------
# 10. Systemd service
# ---------------------------------------------------------------------------
log "Installing systemd unit..."
install -m 644 "${APP_DIR}/deploy/ai-secretary.service" /etc/systemd/system/ai-secretary.service
systemctl daemon-reload
systemctl enable ai-secretary.service
systemctl restart ai-secretary.service

# ---------------------------------------------------------------------------
# 11. Nginx reverse proxy on :80
# ---------------------------------------------------------------------------
log "Configuring nginx reverse proxy..."
install -m 644 "${APP_DIR}/deploy/nginx-ai-secretary.conf" /etc/nginx/sites-available/ai-secretary
ln -sf /etc/nginx/sites-available/ai-secretary /etc/nginx/sites-enabled/ai-secretary
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---------------------------------------------------------------------------
# 12. Firewall (UFW) — open SSH and HTTP
# ---------------------------------------------------------------------------
log "Configuring UFW (SSH + HTTP)..."
ufw allow OpenSSH
ufw allow 80/tcp
yes | ufw enable || true

log "Done. Service status:"
systemctl --no-pager --full status ai-secretary.service || true

cat <<EOF

==============================================================================
 AI Secretary is installed on secr-app-d01.
 UI         : http://172.16.7.215/
 MinIO UI   : http://127.0.0.1:9001 (loopback only; tunnel via SSH if needed)
 Logs       : journalctl -u ai-secretary -f
 Restart    : sudo systemctl restart ai-secretary
 Config     : ${APP_DIR}/.env  (edit, then 'systemctl restart ai-secretary')
==============================================================================
EOF
