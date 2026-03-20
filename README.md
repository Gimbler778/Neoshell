# Personal Cloud File Manager 

Polyglot, Docker-first file manager with a custom TCP protocol:

- Python CLI client (`Typer` + `Rich`)
- Node.js TCP server (`net` module) with file storage
- NeonDB PostgreSQL metadata persistence

## Architecture

- `client/`: CLI sends custom protocol commands over raw TCP.
- `server/`: Handles `LIST`, `DELETE`, and `SEND` commands, stores files, persists metadata.
- `cloud_data` volume: Durable upload storage across container restarts.
- NeonDB: External managed Postgres (not containerized).

## Protocol (Custom over TCP)

Commands are UTF-8 and line-based (`\n` terminated):

- `LIST`
- `DELETE <filename>`
- `SEND <filename> <size_bytes> <sha256_hex>` followed by exactly `<size_bytes>` raw bytes

When `AUTH_TOKEN` is configured, server expects the token immediately after the command:

- `LIST <token>`
- `DELETE <token> <filename>`
- `SEND <token> <filename> <size_bytes> <sha256_hex>`

Server response is one JSON line:

```json
{"ok": true, "message": "..."}
```

or

```json
{"ok": false, "error": "..."}
```

## Quick Start

1. Copy env file:

```bash
cp .env.example .env
```

2. Fill `NEON_DATABASE_URL` in `.env`.

Optional but recommended: set `AUTH_TOKEN` to a long random value.

`DB_SSL=true` is recommended for managed Postgres providers (like Neon).

3. Build and run server:

```bash
docker compose up --build -d server
```

4. Use client commands via Docker Compose (same machine):

```bash
docker compose run --rm client list
docker compose run --rm client upload ./sample.txt
docker compose run --rm client delete sample.txt
```

## Deployment Mode (No VM)

This project can be deployed from your own PC (no cloud VM required):

- Run the server on your host machine with Docker Compose.
- Keep data in the `cloud_data` Docker volume.
- Use Tailscale for remote clients (recommended when ISP uses CGNAT).

### Start Server on Host

```bash
docker compose up -d --build server
docker compose ps
docker compose logs --tail 50 server
```

### Access Model

- `LAN`: clients can use host private IP (example `192.168.1.2`).
- `Public internet + port forwarding`: only works if your ISP gives public IPv4 (no CGNAT).
- `Tailscale`: works through CGNAT and is recommended for private remote access.

## Tailscale Deployment (Recommended)

Detailed no-VM instructions: `docs/DEPLOYMENT_NO_VM.md`.

1. Install and sign in to Tailscale on the server host.
2. Install and sign in to Tailscale on client devices.
3. Find server Tailscale IP (example `100.89.208.126`).
4. Use that IP as `--host` in client commands.

Example:

```bash
docker compose run --rm client list --host 100.89.208.126 --port 4000 --token <AUTH_TOKEN>
```

## Phone Client (Android + Termux)

The project client is a Python CLI. On Android, use Termux:

1. Install Termux and Tailscale app.
2. Connect Tailscale on phone.
3. In Termux, install Python and Git:

```bash
pkg update -y
pkg upgrade -y
pkg install -y python git
```

4. Clone repository and install client dependencies:

```bash
git clone <YOUR_REPO_URL>
cd Neoshell/client
pip install -r requirements.txt
```

5. Run commands against server Tailscale IP:

```bash
python main.py list --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
python main.py upload sample.txt --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
python main.py delete sample.txt --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
```

## Local CLI Usage (without Docker)

From `client/`:

```bash
pip install -r requirements.txt
python main.py --help
```

## Notes

- Server saves files under `/app/uploads` (mapped to Docker volume `cloud_data`).
- Metadata table: `file_metadata(name, size_bytes, sha256, stored_path, created_at)`.
- Filename is sanitized to basename to avoid path traversal.
- For `docker compose run --rm client ...`, use `--host server` when targeting the compose service network.
- `127.0.0.1` inside a client container points to that container itself, not the server container.

## Smoke Test

Run a quick end-to-end check (upload/list/delete) against a running server:

```bash
python scripts/smoke_test.py
```

The script reads `SERVER_HOST`, `SERVER_PORT`, and optional `AUTH_TOKEN` from environment variables.
