# No-VM Deployment Guide

This guide explains how to run the project without renting a cloud VM.

## 1. Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- A valid `.env` file with:
  - `NEON_DATABASE_URL`
  - `SERVER_PORT=4000`
  - `AUTH_TOKEN=<strong-random-token>`
  - `DB_SSL=true`

## 2. Start the Server

From repository root:

```bash
docker compose up -d --build server
docker compose ps
docker compose logs --tail 50 server
```

## 3. Local/LAN Test

From the same machine:

```bash
docker compose run --rm client list --host server --port 4000 --token <AUTH_TOKEN>
```

From another device on the same LAN, use host private IP (example `192.168.1.2`).

## 4. Remote Access Options

### Option A: Public Port Forwarding

Use this only if ISP provides public IPv4 (no CGNAT).

- Forward TCP `4000` from router to host `192.168.1.2:4000`
- Add Windows/Linux firewall allow rule for TCP `4000`

### Option B: Tailscale (Recommended)

Works even under CGNAT.

1. Install Tailscale on server host and sign in.
2. Install Tailscale on each client and sign in.
3. Find server Tailscale IP (example `100.89.208.126`).
4. Use that IP in client commands:

```bash
docker compose run --rm client list --host 100.89.208.126 --port 4000 --token <AUTH_TOKEN>
```

## 5. Android Phone Client (Termux)

```bash
pkg update -y
pkg upgrade -y
pkg install -y python git
git clone <YOUR_REPO_URL>
cd Neoshell/client
pip install -r requirements.txt
python main.py list --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
```

## 6. Keep It Available

If server stops, client operations fail. Keep host awake and Docker running.

```bash
docker compose up -d server
```

## 7. Troubleshooting

- `Connection refused` with `--host 127.0.0.1` from docker client container:
  - Use `--host server` instead.
- `Timeout` from internet:
  - Check CGNAT/public IPv4 status with ISP.
- Auth failures:
  - Ensure same `AUTH_TOKEN` is used by server and client.
