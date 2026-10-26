# Neoshell - Personal Cloud File Manager

Neoshell is a Docker-first file manager with a Python CLI, an HTTP API, S3-compatible object storage, and Neon/PostgreSQL metadata.

## Architecture

| Component | Location | Responsibility |
| --- | --- | --- |
| CLI | `client/` | Streams uploads and calls the REST API. |
| API | `server/` | Authenticates requests, verifies SHA-256, and manages metadata/object storage. |
| Object storage | S3-compatible provider | Stores file bytes durably. |
| Metadata | NeonDB/PostgreSQL | Stores filename, size, checksum, object key, and timestamp. |

## REST API

All `/api` endpoints accept `Authorization: Bearer <AUTH_TOKEN>` when `AUTH_TOKEN` is configured.

- `GET /health` -> `{"ok":true}`
- `GET /api/files` -> list metadata
- `GET /api/files/:name` -> stream file bytes with SHA-256 header
- `POST /api/files` -> raw binary body with `X-File-Name`, `X-SHA256`, and `Content-Length`
- `POST /api/files/:name/share` -> generate temporary presigned S3/B2 download URL (`{"expires_in": 3600}`)
- `DELETE /api/files/:name` -> delete metadata and the S3 object

Filenames are reduced to their basename. Uploads are streamed to object storage and recorded in PostgreSQL only after received byte count and SHA-256 match. Downloads stream to a temporary `.part` file, verify checksum, and rename atomically.

## Prerequisites

- Docker with Compose
- NeonDB or another PostgreSQL database
- An S3-compatible bucket and credentials

Copy `.env.example` to `.env`, then replace every `replace-with-*` value. Never commit `.env`.

## Local Quick Start

Configure the `S3_*` values in `.env` for an S3-compatible provider such as MinIO, Backblaze B2, or Cloudflare R2.

```bash
cp .env.example .env
docker compose up --build -d server
docker compose ps
```

Check the API:

```bash
curl http://localhost:8080/health
```

## Quick Start

### 1. Install the CLI

Install once with `pipx` (recommended) or `pip`:

```bash
pipx install neoshell-cli
# or: pip install neoshell-cli
```

If PyPI has not refreshed yet, or reports `No matching distribution found`,
install the current repository version while developing:

```bash
pip install ./client
```

The package is published from the `release.yml` workflow. New releases are
created by updating the version in `client/pyproject.toml` and pushing a
matching version tag.

### 2. Configure & Connect

```bash
neoshell login --url https://YOUR-APP.koyeb.app --token YOUR_AUTH_TOKEN
```

### 3. File Operations

```bash
# Upload files
neoshell upload ./photo.zip ./notes.txt

# List stored files
neoshell list

# Download a file with automatic SHA-256 integrity check
neoshell download photo.zip

# Create a temporary shareable link (e.g. 24h, 1h, 7d)
neoshell share photo.zip --expires 24h

# Delete a file
neoshell delete photo.zip --yes

# Check status
neoshell status
```

For complete CLI documentation and flags, see [docs/CLI.md](docs/CLI.md).

## Local Development & Docker

Run the server locally with Docker:

```bash
cp .env.example .env
docker compose up --build -d server
curl http://localhost:8080/health
```

Use the CLI against local server:

```bash
# Using installed package
neoshell login --url http://127.0.0.1:8080 --token "$AUTH_TOKEN"
neoshell upload sample.txt

# Or run from repo in development
pip install -e ./client
python -m neoshell list
```

## Public Access & Sharing
 
To share access with collaborators without deploying to cloud VMs, expose your local Docker container with a free Cloudflare tunnel:
 
```bash
npx -y cloudflared tunnel --url http://localhost:8080
```
 
Cloudflare generates an instant public HTTPS URL (e.g. `https://your-name.trycloudflare.com`). Collaborators can then log in from any machine:
 
```bash
neoshell login --url https://your-name.trycloudflare.com --token YOUR_AUTH_TOKEN
neoshell list
```

## Smoke Test

With the server running and the Python dependencies installed:

```bash
python scripts/smoke_test.py
```

The script reads `SERVER_URL` or `SERVER_HOST`/`SERVER_PORT`, plus `AUTH_TOKEN`, from the environment.

## License

See [LICENSE.txt](LICENSE.txt).
