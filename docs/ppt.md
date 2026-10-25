---
marp: true
paginate: true
theme: default
title: Neoshell
---

<!-- Slide 1 -->

# Neoshell

### Personal cloud file manager, driven from the terminal

Docker-first API · S3-compatible storage · Neon PostgreSQL · Python CLI

`github.com/Gimbler778/Neoshell`

---

<!-- Slide 2 -->

## The Problem

Sharing a file from a terminal today means one of:

- Running your own file server (setup, ports, TLS, backups)
- Uploading to a third-party service you do not control
- Emailing or messaging files that are too large

**There is no simple, self-owned, command-line way to store and share files.**

---

<!-- Slide 3 -->

## The Solution

Neoshell splits the responsibilities:

- A **small HTTP API** you deploy once
- **Object storage** for the bytes
- **PostgreSQL** for metadata
- An **installable CLI** for every day use

```bash
neoshell upload ./report.pdf
neoshell list
neoshell share ./report.pdf --expires 24h
```

---

<!-- Slide 4 -->

## Key Features

| Feature | Detail |
| --- | --- |
| Terminal first | Upload, list, delete, download, share |
| Durable storage | Any S3-compatible provider (B2, R2, MinIO) |
| Metadata in Postgres | Name, size, SHA-256, timestamp |
| Integrity checked | Bytes and checksum verified before commit |
| Docker-first | One composition for server and client |
| Low cost | Free-tier friendly deployment stack |
| Portable | Windows, macOS, Linux |

---

<!-- Slide 5 -->

## Architecture

```text
   ┌────────────┐        HTTPS        ┌──────────────┐
   │  Neoshell  │ ──────────────────► │   Express    │
   │    CLI     │   Bearer AUTH_TOKEN │     API      │
   └────────────┘                     └──────┬───────┘
                                             │
                        ┌────────────────────┴──────────────────┐
                        │                                       │
                  ┌─────▼─────┐                          ┌──────▼─────┐
                  │    S3     │                          │ PostgreSQL │
                  │  bucket   │                          │  metadata  │
                  └───────────┘                          └────────────┘
```

Bytes go to object storage. Only verified metadata goes to the database.

---

<!-- Slide 6 -->

## Upload Flow (Integrity First)

1. CLI computes SHA-256 and size of the local file
2. Sends raw binary with `X-File-Name`, `X-SHA256`, `Content-Length`
3. Server streams the body through a hashing transform **into S3**
4. Received byte count and digest are compared with the headers
5. On mismatch: the S3 object is deleted and the request fails
6. On match: metadata is inserted or updated in PostgreSQL

No unverified file ever appears in the listing.

---

<!-- Slide 7 -->

## Tech Stack

| Layer | Choice |
| --- | --- |
| CLI | Python 3.12, Typer, Rich, Requests |
| API | Node.js 20, Express 4 |
| Metadata | Neon / PostgreSQL 16, `pg` |
| Object storage | `@aws-sdk/client-s3` |
| Packaging | Docker multi-stage, distroless non-root |
| CI | GitHub Actions (Postgres + MinIO services) |

---

<!-- Slide 8 -->

## REST API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Unauthenticated health probe |
| `GET` | `/api/files` | List metadata |
| `POST` | `/api/files` | Raw binary upload with checksum headers |
| `DELETE` | `/api/files/:name` | Remove metadata and S3 object |
| `GET` | `/api/files/:name` | Streamed download *(planned)* |
| `POST` | `/api/files/:name/share` | Time-limited presigned URL *(planned)* |

All `/api` routes require `Authorization: Bearer <AUTH_TOKEN>` when a token is configured.

---

<!-- Slide 9 -->

## CLI Today

```bash
pip install -r client/requirements.txt

python client/main.py upload sample.txt \
  --url https://YOUR-APP.example.com --token YOUR_AUTH_TOKEN

python client/main.py list --url https://YOUR-APP.example.com
python client/main.py delete sample.txt --url https://YOUR-APP.example.com
```

Works locally, over LAN, or across Tailscale:

```bash
python client/main.py list --host 192.168.1.2 --port 8080
```

---

<!-- Slide 10 -->

## CLI as a Package (v0.1.0 Target)

```bash
pipx install neoshell-cli
neoshell login --url https://YOUR-APP.koyeb.app --token TOKEN

neoshell upload ./photo.zip ./notes.txt
neoshell list
neoshell download photo.zip
neoshell share photo.zip --expires 24h
neoshell status
neoshell logout
```

No clone. No Docker. No flags on every command.

Distribution name `neoshell-cli`, command name `neoshell`.

---

<!-- Slide 11 -->

## Configuration Model

Precedence, highest first:

1. `--url` / `--token` flags
2. `NEOSHELL_URL` / `NEOSHELL_TOKEN` (legacy `SERVER_URL` / `AUTH_TOKEN`)
3. Saved config file
4. `http://127.0.0.1:8080`

Config location:

| OS | Path |
| --- | --- |
| Linux | `~/.config/neoshell/config.toml` |
| macOS | `~/Library/Application Support/neoshell/config.toml` |
| Windows | `%APPDATA%\neoshell\config.toml` |

Written atomically with `0600` permissions.

---

<!-- Slide 12 -->

## Data Model

```sql
CREATE TABLE IF NOT EXISTS file_metadata (
  name        TEXT PRIMARY KEY,
  size_bytes  BIGINT NOT NULL,
  sha256      TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- `name` is the permissionless-safe basename of the uploaded file
- Re-uploading the same name updates the record and refreshes `created_at`
- The S3 key matches the stored filename

---

<!-- Slide 13 -->

## Deployment: Zero-VM, Free Tier

| Component | Service |
| --- | --- |
| App | Koyeb or Render (Docker web service) |
| Database | Neon PostgreSQL |
| Files | Backblaze B2 or Cloudflare R2 |
| TLS + health | Provided by the platform |

```bash
docker compose up --build -d server
curl http://localhost:8080/health   # {"ok":true}
```

The platform injects `PORT`. Do not hard-code it in cloud deployments.

---

<!-- Slide 14 -->

## Security Posture

- Shared bearer token guards every `/api` route
- `/health` stays public so platform probes work
- Server image runs as non-root on distroless Node
- Uploads are streamed, not buffered in memory
- SHA-256 plus length verification blocks silent corruption
- Secrets live in `.env` or platform environment, never in git
- Presigned share links bypass the token for their lifetime and cannot be revoked

---

<!-- Slide 15 -->

## CI Pipeline

```text
push / pull_request to main
   │
   ├── python-client      syntax check of the CLI
   ├── node-server        syntax check of the API
   └── integration-smoke  Postgres 16 + MinIO
                          start server → /health
                          upload → list → delete
```

The smoke job proves the full path: HTTP → checksum → S3 → database.

---

<!-- Slide 16 -->

## Roadmap

| Phase | Work |
| --- | --- |
| 1 | Package skeleton, saved login, multi-file upload, progress bars |
| 2 | Download endpoint, share links, `download` and `share` commands |
| 3 | Test matrix, Trusted Publishing on `v*` tags, docs rewrite |

Planned: revocable share tokens, per-user auth, resumable transfers, chunked uploads.

---

<!-- Slide 17 -->

## Known Limitations

- Single shared `AUTH_TOKEN`: anyone holding it sees every file
- Share links are presigned S3 URLs and cannot be revoked individually
- One POST per file, so host body-size limits apply
- Free hosts sleep, causing 20–50 s cold starts
- `neoshell` command name collides with an unrelated PyPI package
- No resume for interrupted uploads or downloads

---

<!-- Slide 18 -->

## Demo

```bash
# 1. Start the stack
docker compose up --build -d server

# 2. Authenticate
neoshell login --url http://127.0.0.1:8080 --token "$AUTH_TOKEN"

# 3. Share a file
neoshell upload sample.txt
neoshell list
neoshell share sample.txt --expires 1h

# 4. Fetch it back
neoshell download sample.txt -o ./downloads/
neoshell delete sample.txt --yes
```

---

<!-- Slide 19 -->

## Try It

```bash
pipx install neoshell-cli
neoshell login --url https://YOUR-APP.example.com --token YOUR_TOKEN
```

- Repository: `github.com/Gimbler778/Neoshell`
- Docs: `README.md`, `docs/`
- License: see `LICENSE.txt`

**Your files. Your server. Your terminal.**
