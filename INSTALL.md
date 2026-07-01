# AI Secretary — Installation Guide

End-to-end installation of the AI Secretary stack on a fresh Ubuntu 22.04 LTS server.

| Item | Value |
| --- | --- |
| Hostname | `secr-app-d01` |
| IP | `172.16.7.215` |
| OS | Ubuntu Server 22.04 LTS |
| vCPU | 16 |
| RAM | 32 GB |
| Disk | 350 GB SSD |

The stack consists of:

* **FastAPI + Uvicorn** — web app and HTTP API (runs natively as a systemd service)
* **faster-whisper** — speech-to-text on CPU (runs in-process)
* **Ollama** — local LLM that turns transcripts into meeting protocols
* **PostgreSQL 16** — metadata storage (in Docker)
* **MinIO** — S3-compatible object storage for audio files (in Docker)
* **nginx** — reverse proxy on port 80

There are two installation paths: the **automated** one (`deploy/install.sh`)
and the **manual** one. They produce identical results.

---

## 0. Provision the server

Before anything else, make sure the host is reachable and has the right network identity.

```bash
# from any admin workstation
ssh ubuntu@172.16.7.215
```

On the server, confirm OS and resources:

```bash
lsb_release -a            # → Ubuntu 22.04.x LTS
nproc                     # → 16
free -h                   # → ~32Gi total
df -h /                   # → ~350G
ip -4 addr show           # → 172.16.7.215 on the primary interface
```

Set hostname (the installer also does this):

```bash
sudo hostnamectl set-hostname secr-app-d01
echo "172.16.7.215   secr-app-d01" | sudo tee -a /etc/hosts
```

---

## 1. Copy the project to the server

Upload the `ai-secretary.zip` artifact and unpack it into `/opt`:

```bash
# from your workstation
scp ai-secretary.zip ubuntu@172.16.7.215:/tmp/

# on the server
sudo apt-get update && sudo apt-get install -y unzip
sudo mkdir -p /opt/ai-secretary
sudo unzip -q /tmp/ai-secretary.zip -d /opt/ai-secretary
# If the zip contains a top-level folder, move its contents up:
# sudo mv /opt/ai-secretary/ai-secretary/* /opt/ai-secretary/ && sudo rmdir /opt/ai-secretary/ai-secretary
cd /opt/ai-secretary
```

---

## 2. Edit the environment file

Copy and edit secrets **before** the first launch:

```bash
sudo cp .env.example .env
sudo nano .env
```

Replace at minimum:

* `POSTGRES_PASSWORD` — a strong random password
* `MINIO_SECRET_KEY` — a strong random password
* `DATABASE_URL` — keep the user/password/host consistent with the above
* `OLLAMA_MODEL` — pick a model your RAM can afford (defaults are sane)
* `WHISPERX_MODEL` — `large-v3` recommended on this hardware (CPU, int8)

Lock the file down:

```bash
sudo chmod 600 .env
```

---

## 3a. Automated install (recommended)

```bash
sudo bash /opt/ai-secretary/deploy/install.sh
```

This will:

1. Install OS packages (Python 3.10, ffmpeg, build tools, nginx, ufw, libpq-dev)
2. Install Docker Engine + Compose plugin from the official Docker repo
3. Install Ollama natively and enable it on boot
4. Create the `aisec` service user
5. Sync the repo into `/opt/ai-secretary`, create a venv, install Python requirements
6. Bring up PostgreSQL + MinIO containers (bound to `127.0.0.1`)
7. Run Alembic migrations
8. Pull the Ollama model defined in `.env`
9. Install and start the `ai-secretary.service` systemd unit
10. Configure nginx as a reverse proxy on port 80
11. Enable UFW (SSH + HTTP)

When it finishes, the UI is at `http://172.16.7.215/`.

---

## 3b. Manual install (step by step)

If you would rather run each step by hand, follow this section instead of 3a.

### 3b.1 OS packages

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates curl gnupg lsb-release \
  build-essential pkg-config git unzip \
  python3.10 python3.10-venv python3.10-dev python3-pip \
  ffmpeg libpq-dev \
  nginx ufw rsync
```

### 3b.2 Docker Engine + Compose plugin

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

### 3b.3 Ollama (LLM runtime)

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama --version
```

### 3b.4 Service user

```bash
sudo useradd --system --create-home \
  --shell /usr/sbin/nologin --home-dir /home/aisec aisec
sudo usermod -aG docker aisec
sudo chown -R aisec:aisec /opt/ai-secretary
```

### 3b.5 Python virtual environment

```bash
sudo -u aisec python3.10 -m venv /opt/ai-secretary/.venv
sudo -u aisec /opt/ai-secretary/.venv/bin/pip install --upgrade pip wheel
sudo -u aisec /opt/ai-secretary/.venv/bin/pip install -r /opt/ai-secretary/requirements.txt
```

The first install pulls ~2 GB (PyTorch CPU wheels + ctranslate2 for faster-whisper).

### 3b.6 Bring up Postgres + MinIO

```bash
cd /opt/ai-secretary
sudo -u aisec docker compose --env-file .env up -d
sudo -u aisec docker compose ps          # both should be (healthy)
```

### 3b.7 Database migrations

```bash
cd /opt/ai-secretary
sudo -u aisec bash -c 'set -a; source .env; set +a; \
  /opt/ai-secretary/.venv/bin/alembic -c alembic.ini upgrade head'
```

### 3b.8 Pull the Ollama model

```bash
# matches the OLLAMA_MODEL value in .env
ollama pull qwen2.5:7b
```

Recommended models on 32 GB RAM (CPU-only):

| Model | RAM | Quality |
| --- | --- | --- |
| `qwen2.5:3b` | ~3 GB | fast, basic |
| `qwen2.5:7b` | ~6 GB | balanced (default) |
| `qwen2.5:14b` | ~10 GB | higher quality |
| `llama3.1:8b` | ~6 GB | strong English, OK Russian |

### 3b.9 systemd unit

```bash
sudo install -m 644 /opt/ai-secretary/deploy/ai-secretary.service \
  /etc/systemd/system/ai-secretary.service
sudo systemctl daemon-reload
sudo systemctl enable --now ai-secretary.service
sudo systemctl status ai-secretary.service --no-pager
```

### 3b.10 nginx reverse proxy

```bash
sudo install -m 644 /opt/ai-secretary/deploy/nginx-ai-secretary.conf \
  /etc/nginx/sites-available/ai-secretary
sudo ln -sf /etc/nginx/sites-available/ai-secretary /etc/nginx/sites-enabled/ai-secretary
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 3b.11 Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw --force enable
sudo ufw status verbose
```

---

## 4. Smoke test

```bash
# from the server itself
curl -s http://127.0.0.1:8000/protocols
# → []   (empty list = API is up)

# from your workstation
curl -s http://172.16.7.215/protocols
# → []
```

Open `http://172.16.7.215/` in a browser, drop an MP3/WAV/M4A file into the
upload area and wait. The page shows live progress; large files plus a small
Whisper/Ollama model can take several minutes on CPU.

---

## 5. Day-2 operations

```bash
# tail logs
sudo journalctl -u ai-secretary -f

# restart after editing .env or requirements.txt
sudo systemctl restart ai-secretary

# update Python deps
sudo -u aisec /opt/ai-secretary/.venv/bin/pip install -r /opt/ai-secretary/requirements.txt
sudo systemctl restart ai-secretary

# inspect dockerized services
sudo -u aisec docker compose -f /opt/ai-secretary/docker-compose.yml ps
sudo -u aisec docker compose -f /opt/ai-secretary/docker-compose.yml logs --tail=200 postgres minio

# MinIO console (loopback only — tunnel via SSH from your workstation)
ssh -L 9001:127.0.0.1:9001 ubuntu@172.16.7.215
# then open http://127.0.0.1:9001 in your local browser

# backup Postgres
sudo -u aisec docker exec aisec_postgres \
  pg_dump -U aisec aisec | gzip > /var/backups/aisec-$(date +%F).sql.gz
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `ai-secretary.service` keeps restarting | bad `.env` or missing Postgres password | `journalctl -u ai-secretary -n 100` |
| `psycopg2.OperationalError: connection refused` | Postgres container not healthy yet | `docker compose ps`, wait, then `systemctl restart ai-secretary` |
| `Ollama: connection refused` | Ollama service down | `sudo systemctl restart ollama` |
| Long upload times out at nginx | body too large / read timeout | already raised to 1 GB / 1 h in the provided nginx config |
| Whisper crashes with `Killed` | OOM (model too big for RAM) | downgrade `WHISPERX_MODEL` to `medium` or `small` |
| `Permission denied` on `docker` for aisec | user not in docker group yet | `sudo usermod -aG docker aisec && sudo systemctl restart ai-secretary` |

---

## 7. Uninstall

```bash
sudo systemctl disable --now ai-secretary
sudo rm /etc/systemd/system/ai-secretary.service
sudo rm /etc/nginx/sites-enabled/ai-secretary /etc/nginx/sites-available/ai-secretary
sudo systemctl reload nginx
cd /opt/ai-secretary && sudo -u aisec docker compose down -v
sudo rm -rf /opt/ai-secretary
sudo userdel -r aisec
```
