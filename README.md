# Personal Cloud File Manager (Advanced)

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

3. Build and run server:

```bash
docker compose up --build -d server
```

4. Use client commands via Docker Compose:

```bash
docker compose run --rm client list
docker compose run --rm client upload ./sample.txt
docker compose run --rm client delete sample.txt
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
