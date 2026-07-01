#!/usr/bin/env bash
# Convenience launcher for development on the operator's laptop.
# In production on secr-app-d01 the service is managed by systemd
# (see deploy/ai-secretary.service).
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo ".env not found — copy .env.example to .env and edit secrets" >&2
  exit 1
fi

set -a; source .env; set +a

echo "[run.sh] Starting Docker services (postgres, minio)..."
docker compose up -d

echo "[run.sh] Waiting for PostgreSQL..."
until docker exec aisec_postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
  sleep 1
done
echo "[run.sh] PostgreSQL is ready."

echo "[run.sh] Running Alembic migrations..."
alembic upgrade head

echo "[run.sh] Starting FastAPI (uvicorn)..."
exec uvicorn app.main:app \
  --host "${APP_HOST:-0.0.0.0}" \
  --port "${APP_PORT:-8000}" \
  --workers "${APP_WORKERS:-2}"
