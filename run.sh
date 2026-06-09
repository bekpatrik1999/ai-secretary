#!/usr/bin/env bash
set -e

echo "Starting Docker services..."
docker compose up -d

echo "Waiting for PostgreSQL to be ready..."
until docker exec aisec_postgres pg_isready -U user -d aisec > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting FastAPI server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
