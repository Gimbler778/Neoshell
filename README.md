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
- `POST /api/files` -> raw binary body with `X-File-Name`, `X-SHA256`, and `Content-Length`
- `DELETE /api/files/:name` -> delete metadata and the S3 object

Filenames are reduced to their basename. Uploads are streamed to object storage and are recorded in PostgreSQL only after the received byte count and SHA-256 match the request headers.

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

Use the CLI:

```bash
docker compose run --rm -v "${PWD}/sample.txt:/app/sample.txt" client upload sample.txt
docker compose run --rm client list
docker compose run --rm client delete sample.txt
```

## CLI Configuration

For a deployed service:

```bash
pip install -r client/requirements.txt
python client/main.py list --url https://YOUR-APP.example.com --token YOUR_AUTH_TOKEN
python client/main.py upload sample.txt --url https://YOUR-APP.example.com --token YOUR_AUTH_TOKEN
```

For local/LAN use, `--host` and `--port` remain available and default to `127.0.0.1:8080`. `SERVER_URL` can also be used instead of `--url`.

## Free Cloud Deployment

The recommended no-card MVP stack is Koyeb or Render for the Docker web service, Backblaze B2 for S3-compatible storage, and Neon for PostgreSQL. Cloudflare R2 is also supported, but account activation may request a payment method.

1. Create a Neon project and copy its pooled connection string into `NEON_DATABASE_URL`. Set `DB_SSL=true`.
2. Create a private Backblaze B2 bucket, an application key restricted to that bucket, and note the S3 endpoint, for example `https://s3.us-west-004.backblazeb2.com`.
3. Deploy this repository as a Docker web service. The service must use the `server/Dockerfile`; the platform supplies `PORT`.
4. Add these environment variables to the service: `NEON_DATABASE_URL`, `DB_SSL`, `AUTH_TOKEN`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`, `S3_ENDPOINT`, and `S3_FORCE_PATH_STYLE=false`.
5. Configure the health check as `GET /health`. Do not set a fixed cloud `PORT`; let the platform provide it.
6. Verify `https://YOUR-APP.example.com/health`, then use that URL with the CLI.

For Cloudflare R2, use the account S3 endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, an R2 API token, the bucket name, `S3_REGION=auto`, and `S3_FORCE_PATH_STYLE=false`.

Free web services may sleep after inactivity, so the first request can have a cold-start delay. Large uploads may also be limited by the platform's HTTP body-size limit; chunked uploads can be added later if needed.

## LAN and Tailscale

The API is ordinary HTTP, so local access still works over LAN or Tailscale:

```bash
python client/main.py list --host 192.168.1.2 --port 8080 --token YOUR_AUTH_TOKEN
python client/main.py list --url http://100.x.y.z:8080 --token YOUR_AUTH_TOKEN
```

## Smoke Test

With the server running and the Python dependencies installed:

```bash
python scripts/smoke_test.py
```

The script reads `SERVER_URL` or `SERVER_HOST`/`SERVER_PORT`, plus `AUTH_TOKEN`, from the environment.

## License

See [LICENSE.txt](LICENSE.txt).
