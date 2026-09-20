# Neoshell — Personal Cloud File Manager

Neoshell is a self-hosted, polyglot file manager designed to run Docker-first with zero dependency on a cloud VM. It exposes a simple custom TCP protocol and is built from three loosely coupled components:

- **Client** — a Python CLI built with [`Typer`](https://typer.tiangolo.com/) and [`Rich`](https://rich.readthedocs.io/).
- **Server** — a Node.js TCP server (built on the `net` module) responsible for file storage and protocol handling.
- **Metadata store** — NeonDB (managed PostgreSQL) for lightweight persistence.

## Table of Contents

- [Architecture](#architecture)
- [Protocol](#protocol)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Deployment](#deployment)
  - [Deployment Model](#deployment-model)
  - [Start the Server](#start-the-server)
  - [Remote Access Strategies](#remote-access-strategies)
  - [Tailscale (Recommended)](#tailscale-recommended)
  - [Android Phone Client (Termux)](#android-phone-client-termux)
- [Local Development](#local-development)
- [Smoke Test](#smoke-test)
- [Notes](#notes)

## Architecture

| Component | Location | Technology | Responsibility |
| --- | --- | --- | --- |
| CLI client | `client/` | Python (Typer + Rich) | Sends custom protocol commands over raw TCP. |
| TCP server | `server/` | Node.js (`net`) | Handles `LIST`, `DELETE`, and `SEND`; stores files; persists metadata. |
| Storage | `cloud_data` volume | Docker volume | Durable upload storage across container restarts at `/app/uploads`. |
| Metadata | NeonDB | Managed PostgreSQL | External, non-containerized persistence for file records. |

Both application containers are defined in a single `docker-compose.yml`, so the entire stack runs on a single host.

## Protocol

Neoshell uses a line-based, UTF-8 TCP protocol. Commands are terminated by `\n`, and every command produces exactly one JSON line in response.

### Commands (without authentication)

```
LIST
DELETE <filename>
SEND <filename> <size_bytes> <sha256_hex>
```

`SEND` is followed immediately by exactly `<size_bytes>` of raw binary payload.

### Commands (with `AUTH_TOKEN` configured)

When an auth token is set, it is appended immediately after the command word:

```
LIST <token>
DELETE <token> <filename>
SEND <token> <filename> <size_bytes> <sha256_hex>
```

### Responses

Success (general commands):

```json
{"ok": true, "message": "..."}
```

Success (`LIST`):

```json
{"ok": true, "files": [{"name": "...", "size_bytes": 123, "sha256": "...", "created_at": "..."}]}
```

Failure:

```json
{"ok": false, "error": "..."}
```

## Prerequisites

- **Docker** with the Compose plugin (Docker Desktop on Windows/macOS, Docker Engine + Compose on Linux).
- A **NeonDB** (or any managed PostgreSQL) database and its connection URL.
- A valid `.env` file. Copy the template and fill it in:

```bash
cp .env.example .env
```

The file must contain:

| Variable | Purpose |
| --- | --- |
| `NEON_DATABASE_URL` | Managed Postgres connection string. |
| `SERVER_PORT` | TCP port the server listens on (default `4000`). |
| `AUTH_TOKEN` | Shared secret required by server and client (recommended). Use a long random value. |
| `DB_SSL` | Set to `true` for managed Postgres providers such as Neon. |

## Quick Start

1. Copy and configure the environment file:

```bash
cp .env.example .env
```

2. Set a strong random `AUTH_TOKEN` and your `NEON_DATABASE_URL`.

3. Build and start the server:

```bash
docker compose up --build -d server
```

4. Verify the stack:

```bash
docker compose ps
docker compose logs --tail 50 server
```

## Usage

All client commands can be run through Docker Compose on the same machine as the server:

```bash
docker compose run --rm client list
docker compose run --rm -v "${PWD}/sample.txt:/app/sample.txt" client upload sample.txt
docker compose run --rm client delete sample.txt
```

> [!NOTE]
> The client container only contains `main.py`, so a file to upload must be passed in via a volume mount (as shown above). Use the in-container path as the argument.

> [!NOTE]
> Use `--host server` when invoking the client container, or let the compose `client` service default to it. `127.0.0.1` inside a container refers to the container itself, not the server container.

## Deployment

There is no reliance on a free-tier cloud provider. The project is designed to be self-hosted from a personal computer (or any always-on device) using Docker Compose, with connectivity handled by third-party network tools.

### Deployment Model

- The **server runs on the host machine** via Docker Compose.
- Files are kept in the persistent `cloud_data` Docker volume.
- Remote access is provided by either:
  - **LAN** — clients connect to the host's private IP (e.g. `192.168.1.2`).
  - **Public internet + port forwarding** — viable only if the ISP provides a public IPv4 address (no CGNAT).
  - **Tailscale** — a third-party mesh VPN that works even behind CGNAT and is the recommended approach for private remote access.

### Start the Server

```bash
docker compose up -d --build server
docker compose ps
docker compose logs --tail 50 server
```

### Remote Access Strategies

| Scenario | Access | Recommendation |
| --- | --- | --- |
| Same LAN | Host private IP | Simple, no extra tooling. |
| Public IPv4 | Forward TCP `4000` on router + allow firewall rule | Only when ISP offers public IPv4. |
| CGNAT / anywhere | Tailscale | Recommended. |

### Tailscale (Recommended)

Tailscale gives devices private, end-to-end encrypted connectivity regardless of network topology. For detailed instructions, see [docs/DEPLOYMENT_NO_VM.md](docs/DEPLOYMENT_NO_VM.md).

1. Install and sign in to Tailscale on the server host.
2. Install and sign in to Tailscale on each client device.
3. Note the server's Tailscale IP (e.g. `100.89.208.126`).
4. Use that IP as `--host` in all client commands:

```bash
docker compose run --rm client list --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
```

### Android Phone Client (Termux)

The project client is a Python CLI. On Android, run it inside [Termux](https://termux.com/) and connect the phone to Tailscale:

1. Install **Termux** and the **Tailscale** app, then sign in to Tailscale on the phone.
2. Install Python and Git in Termux:

```bash
pkg update -y
pkg upgrade -y
pkg install -y python git
```

3. Clone the repository and install client dependencies:

```bash
git clone https://github.com/Gimbler778/Neoshell.git
cd Neoshell/client
pip install -r requirements.txt
```

4. Manage files against the server's Tailscale IP:

```bash
python main.py list --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
python main.py upload sample.txt --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
python main.py delete sample.txt --host <SERVER_TAILSCALE_IP> --port 4000 --token <AUTH_TOKEN>
```

## Local Development

Run the CLI without Docker from `client/`:

```bash
pip install -r requirements.txt
python main.py --help
```

## Smoke Test

Run an end-to-end upload/list/delete check against a running server:

```bash
python scripts/smoke_test.py
```

The script reads `SERVER_HOST`, `SERVER_PORT`, and optional `AUTH_TOKEN` from environment variables.

## Notes

- Server files live under `/app/uploads`, mapped to the `cloud_data` Docker volume.
- Metadata is stored in the `file_metadata` table (`name`, `size_bytes`, `sha256`, `stored_path`, `created_at`).
- Uploaded filenames are reduced to their basename to prevent path traversal.
- Keep the host awake and Docker running — if the server stops, remote clients cannot connect.

## License

See [LICENSE.txt](LICENSE.txt).