# Neoshell: Comprehensive Project Engineering & Lifecycle Report

**Project Name:** Neoshell (`neoshell-cli`)  
**Repository:** [github.com/Gimbler778/Neoshell](https://github.com/Gimbler778/Neoshell)  
**Package:** [`neoshell-cli` on PyPI](https://pypi.org/project/neoshell-cli/) (v0.1.0)  
**Authors:** Gimbler778 & Contributors  
**Date:** October 2026  
**Status:** Production / v0.1.0 Released  

---

## 1. Executive Summary

Neoshell is a personal, terminal-driven cloud file management and sharing platform designed for developers, systems engineers, and technical users who require seamless file transfers directly from the command line without sacrificing ownership, durability, or data integrity.

The project represents a complete full-stack, cloud-native engineering journey that began in February 2026 as an experimental custom TCP socket server storing files on local Docker volumes, and evolved into a robust, enterprise-grade architecture featuring:
- A distributed, serverless cloud backend powered by **Node.js 20 and Express**, backed by **S3-compatible object storage** (Backblaze B2, Cloudflare R2, MinIO, or AWS S3) and **Neon Serverless PostgreSQL**.
- A modern, cross-platform CLI tool packaged and published on PyPI as **`neoshell-cli`**, built with **Python 3, Typer, and Rich**, supporting single-command installation (`pipx install neoshell-cli`), persistent local authentication, atomic configuration management, and full visual progress bars.
- End-to-end data integrity guarantees using streaming SHA-256 hashing during both upload and download, with automated rollback on transmission corruption.
- Temporary, time-bounded public file sharing via cryptographically signed presigned S3 URLs with native operating system clipboard integration.
- A hardened multi-platform CI/CD testing pipeline running unit, CLI, and integration smoke tests across Linux, macOS, and Windows against live PostgreSQL and S3 mock services, accompanied by automated PyPI release workflows via PyPA Trusted Publishing (OIDC).

This report documents the end-to-end lifecycle of the Neoshell project: the underlying problem statement, architectural pivots, chronological commit history, in-depth technical specifications, engineering hurdles faced, testing validations, and future roadmap.

---

## 2. Motivation & Problem Statement

### The Terminal File Sharing Dilemma
Modern developers spend a substantial amount of their working day inside terminal emulators, remote SSH sessions, or container environments. However, transferring, sharing, or backing up files from the command line typically forces users into painful trade-offs:
1. **Third-Party Pastebins and Ephemeral File Services:** Services such as wetransfer, transfer.sh, or temporary upload sites are quick, but they require surrendering private file bytes to untrusted third-party infrastructure with unpredictable retention limits and privacy concerns.
2. **Traditional Self-Hosted Storage (FTP, Nextcloud, MinIO UI):** Self-hosting full web suites like Nextcloud or raw MinIO clusters requires maintaining persistent virtual machines, setting up reverse proxies, configuring TLS certificates, and dealing with dynamic DNS, port forwarding, and storage drive backups.
3. **Clumsy CLI Ergonomics:** Cloud providers (AWS CLI, B2 CLI, Google Cloud Storage CLI) provide command-line utilities, but their configurations require complex IAM policies, credential files, complex multi-flag parameters, and lack streamlined commands for generating human-friendly temporary share links or verifying file integrity on the fly.

### The Neoshell Mission
Neoshell was conceived to deliver the best of both worlds:
- **Zero-Friction CLI UX:** Simple commands like `neoshell upload <file>`, `neoshell list`, `neoshell download <file>`, and `neoshell share <file> --expires 24h` without typing server URLs or credentials on every call.
- **True Infrastructure Ownership:** The user controls where their bytes live (S3/B2/R2) and where their metadata resides (PostgreSQL).
- **Zero-VM / Free-Tier Friendly:** The server component requires no persistent disk storage or dedicated virtual machines; it runs seamlessly on modern serverless container platforms (e.g., Koyeb, Render) with zero operational cost on idle free tiers.
- **Strict Cryptographic Integrity:** No file is accepted or committed to the database without matching size and SHA-256 checksums verified in real-time during streaming.

---

## 3. Architecture & Technical Evolution

The Neoshell platform underwent three distinct architectural evolutions, shifting from a low-level socket prototype into a distributed, cloud-native file storage system.

```
+-----------------------------------------------------------------------------------+
|                              ARCHITECTURAL EVOLUTION                              |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  PHASE 1 (Feb 2026)             PHASE 2 (Sep 2026)          PHASE 3 (Oct 2026)    |
|  Raw TCP Protocol               HTTP REST + Cloud S3        Packaged CLI & PyPI   |
|                                                                                   |
|  +-----------------+           +-----------------+          +-----------------+   |
|  | Python CLI      |           | Python CLI      |          | neoshell-cli    |   |
|  | (socket module) |           | (requests)      |          | (Typer + Rich)  |   |
|  +--------+--------+           +--------+--------+          +--------+--------+   |
|           | TCP (Raw)                   | HTTP REST                  | HTTP + OIDC|
|  +--------v--------+           +--------v--------+          +--------v--------+   |
|  | Node.js net TCP |           | Express HTTP    |          | Express HTTP    |   |
|  +---+---------+---+           +---+---------+---+          +---+---------+---+   |
|      |         |                   |         |                  |         |       |
|  +---v---+ +---v---+           +---v---+ +---v---+          +---v---+ +---v---+   |
|  | Local | | Neon  |           | Cloud | | Neon  |          | S3/B2 | | Neon  |   |
|  | Disk  | | Post- |           | S3/B2 | | Post- |          | R2    | | Post- |   |
|  | Vol   | | gres  |           | (AWS) | | gres  |          | Presign | gres  |   |
|  +-------+ +-------+           +-------+ +-------+          +-------+ +-------+   |
+-----------------------------------------------------------------------------------+
```

### Phase 1: The Raw TCP Socket Genesis (February 2026)
In its initial commit (`4d6cb05`), Neoshell was constructed as a polyglot system communicating over a custom, UTF-8 line-delimited TCP socket protocol:
- **Server:** Node.js native `net` module listening on a TCP port (default `8080`).
- **Client:** Python script utilizing the standard `socket` library.
- **Protocol:**
  - `LIST\n` -> Returned JSON metadata.
  - `DELETE <filename>\n` -> Removed file from disk and database.
  - `SEND <filename> <size_bytes> <sha256_hex>\n` -> Followed immediately by raw binary stream of length `<size_bytes>`.
- **Storage:** Bytes were written to the local container filesystem under `/app/uploads` and mounted to a Docker named volume (`cloud_data`).
- **Database:** Metadata was stored in Neon Serverless PostgreSQL within table `file_metadata`.

#### Limitations of the TCP Architecture:
While fast and lightweight for local Docker setups, this design faced insurmountable roadblocks in modern cloud environments:
1. **PaaS Incompatibility:** Modern zero-cost container platforms (Render, Koyeb, Railway, Fly.io, Vercel) terminate connections at HTTP/HTTPS reverse proxies. They do not route arbitrary raw TCP traffic on arbitrary ports without expensive dedicated IP/VM allocations.
2. **Ephemeral Disks:** Modern web services destroy container filesystems on restart. Storing files in `/app/uploads` required persistent block volumes, which are either unsupported or costly on free tiers.
3. **No Native TLS / CDN Support:** A custom TCP protocol could not easily take advantage of Cloudflare edge networks, SSL termination, or standard web security headers.

### Phase 2: The Cloud-Native Pivot — HTTP REST & S3 Storage (September 2026)
In September 2026 (`f28834c`), the entire backend stack was re-engineered:
- **Express HTTP REST API:** Replaced the Node.js `net` socket server with an Express 4 RESTful API.
- **S3-Compatible Object Storage:** File byte storage was decoupled from the compute instance and migrated to standard S3 object storage APIs via `@aws-sdk/client-s3`. This unlocked compatibility with:
  - **Backblaze B2** (10 GB free storage, S3-compatible API).
  - **Cloudflare R2** (10 GB free storage, zero egress fees).
  - **MinIO** (for local testing, offline setups, or private hardware).
  - **AWS S3** (for enterprise scalability).
- **Stateless Zero-VM Execution:** Because the server now holds zero local state (metadata in Neon, bytes in S3), the server container can run anywhere: on a free Koyeb web service, Render web service, or local Docker exposed via a free Cloudflare Tunnel (`npx -y cloudflared tunnel --url http://localhost:8080`).

### Phase 3: The CLI Packaging & Feature Expansion (October 2026)
In late October 2026 (`ec5fb34` through `e3afd80`), the user experience underwent a quantum leap:
- **Package Architecture (`neoshell-cli`):** The monolithic `client/main.py` was dismantled and refactored into a standard Python package structure using `hatchling` conforming to PEP 517, 518, and 621.
- **Published to PyPI:** Made installable on any operating system with `pipx install neoshell-cli` or `pip install neoshell-cli`.
- **Download Functionality:** Implemented `GET /api/files/:name` streaming with SHA-256 verification and atomic staging.
- **Presigned Share URLs:** Added `POST /api/files/:name/share` integrating `@aws-sdk/s3-request-presigner` to generate cryptographically signed download URLs with custom expirations (1 hour, 24 hours, 7 days) and direct clipboard copying.
- **State Persistence:** Introduced atomic config persistence in user configuration directories (`platformdirs`), eliminating the need to pass `--url` and `--token` on every invocation.

---

## 4. Chronological Commit History & Lifecycle Analysis

The repository contains 18 carefully sequenced commits tracking the development, hardening, refactoring, and distribution of Neoshell:

| Commit Hash | Date | Author | Summary & Technical Description |
| :--- | :--- | :--- | :--- |
| `4d6cb05` | 2026-02-25 | Gimbler778 | **Initial Commit:** Created initial project structure. Node.js raw TCP server (`net`), Python CLI client using raw sockets, Neon PostgreSQL connection pool (`pg`), and Docker Compose setup. |
| `5d8f892` | 2026-02-25 | Gimbler778 | **Base Project and Dockerized:** Added initial GitHub Actions CI workflow skeleton (`.github/workflows/integrate.yml`), comprehensive `.gitignore`, and MIT License (`LICENSE.txt`). |
| `8795806` | 2026-02-25 | Gimbler778 | **variable change:** Standardized environment variable naming in `.env.example` to ensure smooth configuration ingestion. |
| `1073b24` | 2026-02-25 | Gimbler778 | **updated workflow:** Refined GitHub Actions CI workflow step definitions, environment variable injections, and service linkages. |
| `46dbfb1` | 2026-02-25 | Gimbler778 | **updated server image:** Created optimized multi-stage build in `server/Dockerfile` and added `server/.dockerignore` to trim container image size. |
| `98b1f39` | 2026-02-25 | Gimbler778 | **non-root server and fixed volume permissions:** Security hardening. Updated Docker configuration to run server as non-root user `node` and ensured volume permissions on `/app/uploads` mapped correctly. |
| `fc87199` | 2026-02-25 | Gimbler778 | **changed Readme:** Clarified project documentation, running instructions, and volume mounting guidelines. |
| `e89834c` | 2026-03-20 | Gimbler778 | **added patches_fixes:** Implemented automated integration smoke test script (`scripts/smoke_test.py`), upgraded CI pipeline with health checks, and resolved socket buffer edge cases. |
| `b4ec9fc` | 2026-03-21 | Gimbler778 | **deployed:** Added `docs/DEPLOYMENT_NO_VM.md` detailing initial deployment strategies on zero-cost cloud providers. |
| `baa3e71` | 2026-03-22 | Aditya Singh Kushwaha | **Update clone URL in README.md:** Corrected repository clone URL to point to canonical GitHub remote. |
| `c64ad55` | 2026-09-20 | Gimbler778 | **Rewrite README with formal documentation and deployment guide:** Substantial documentation overhaul outlining system architecture, requirements, and deployment runbooks. |
| `5ed704b` | 2026-09-21 | Gimbler778 | **Fix upload example and LIST response shape in README:** Fixed discrepancy in documented JSON response shapes and command syntax. |
| `f28834c` | 2026-09-25 | Gimbler778 | **Update Neoshell cloud file manager stack:** The foundational architectural pivot. Migrated from raw TCP socket server to Express HTTP REST API and from local disk storage to S3-compatible cloud object storage (`@aws-sdk/client-s3`). |
| `ec5fb34` | 2026-10-25 | Gimbler778 | **Package CLI tool, add download and share endpoints:** Massive client refactoring and feature expansion. Created `neoshell-cli` package (`pyproject.toml`, `hatchling`), modular package under `client/src/neoshell/`, config persistence, download endpoint with SHA-256 verification, presigned share endpoint with expiry, 35 unit/CLI tests, and release workflow. |
| `275aabc` | 2026-10-25 | Gimbler778 | **Fix MinIO CI container initialization:** Addressed container race conditions during automated CI runs when initializing MinIO test buckets. |
| `8c7ab15` | 2026-10-25 | Gimbler778 | **Switch CI S3 mock to adobe/s3mock:** Solved CI flakiness by replacing MinIO with `adobe/s3mock:latest`, leveraging automatic bucket provisioning (`initialBuckets=ci-neoshell`) and polling HTTP health checks. |
| `5c6c1b6` | 2026-10-25 | Gimbler778 | **Add presentation deck for Neoshell:** Added slide deck (`docs/ppt.md`) formatted for Marp, detailing problem, solution, architecture, data flow, and roadmap. |
| `e3afd80` | 2026-10-26 | Gimbler778 | **Document published PyPI installation:** Published release `v0.1.0` of `neoshell-cli` to PyPI; updated `README.md`, `docs/CLI.md`, and `docs/DEPLOYMENT_NO_VM.md` with official `pipx install neoshell-cli` instructions. |

---

## 5. Technical Architecture Deep Dive

### 5.1 System Component Topology

```
+-----------------------------------------------------------------------------------+
|                               SYSTEM TOPOLOGY                                     |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|    +-------------------------------------------------------------------------+    |
|    |                           CLIENT LAYER                                  |    |
|    |                                                                         |    |
|    |   neoshell login / upload / list / download / share / delete / status   |    |
|    |   +-----------------------------------------------------------------+   |    |
|    |   | cli.py (Typer UI, parameter parsing, human-friendly UX)         |   |    |
|    |   +--------------------------------+--------------------------------+   |    |
|    |                                    |                                    |    |
|    |         +--------------------------+--------------------------+         |    |
|    |         |                                                     |         |    |
|    |   +-----v----------------------+               +--------------v-----+   |    |
|    |   | config.py                  |               | formatting.py      |   |    |
|    |   | - Atomic TOML persistence  |               | - Rich tables      |   |    |
|    |   | - 4-tier precedence        |               | - Progress bars    |   |    |
|    |   | - platformdirs pathing     |               | - Clipboard copy   |   |    |
|    |   +----------------------------+               +--------------------+   |    |
|    |                                    |                                    |    |
|    |                         +----------v---------+                          |    |
|    |                         | api.py (ApiClient) |                          |    |
|    |                         | - HTTP streaming   |                          |    |
|    |                         | - SHA-256 digest   |                          |    |
|    |                         | - Error mapping    |                          |    |
|    |                         +----------+---------+                          |    |
|    +------------------------------------|------------------------------------+    |
|                                         | HTTPS / Authorization: Bearer           |
|                                         v                                         |
|    +-------------------------------------------------------------------------+    |
|    |                           SERVER LAYER                                  |    |
|    |                                                                         |    |
|    |                         Node 20 Express API                             |    |
|    |                         (server/src/index.js)                           |    |
|    |                                                                         |    |
|    |   - GET  /health                   - GET  /api/files                    |    |
|    |   - POST /api/files                - GET  /api/files/:name              |    |
|    |   - POST /api/files/:name/share    - DELETE /api/files/:name            |    |
|    |   +-----------------------------------------------------------------+   |    |
|    |   | Security: Bearer Auth Token, Path Sanitization (basename)       |   |    |
|    |   | Streaming: Pass-through stream hashing via crypto.createHash    |   |    |
|    |   +-------------------+-------------------------+-------------------+   |    |
|    +-----------------------|-------------------------|-----------------------+    |
|                            |                         |                            |
|             Raw File Bytes |                         | Verified Metadata Records  |
|             (Pass-Through) |                         | (Upsert / Query / Delete)  |
|                            v                         v                            |
|    +----------------------------------+   +----------------------------------+    |
|    |       OBJECT STORAGE LAYER       |   |          DATABASE LAYER          |    |
|    |                                  |   |                                  |    |
|    |  S3-Compatible Object Store      |   |  Neon Serverless PostgreSQL      |    |
|    |  (Backblaze B2, Cloudflare R2,   |   |                                  |    |
|    |   MinIO, or AWS S3)              |   |  Table: file_metadata            |    |
|    |  - Object Key: Sanitized Name    |   |  - name (PK)                     |    |
|    |  - Durable Raw Byte Storage      |   |  - size_bytes                    |    |
|    |  - Presigned Download URLs       |   |  - sha256                        |    |
|    +----------------------------------+   |  - stored_path                   |    |
|                                           |  - created_at                    |    |
|                                           +----------------------------------+    |
+-----------------------------------------------------------------------------------+
```

### 5.2 The Integrity-First Streaming Upload Pipeline
A major technical strength of Neoshell is that large files never buffer entirely into Node.js server RAM, and corrupted uploads never contaminate the database.

1. **Client Pre-Computation:**
   - The CLI opens the source file locally and streams its bytes through Python's `hashlib.sha256()` to calculate the exact hex digest and total byte size.
2. **Streaming HTTP Transmission:**
   - The client initiates an HTTP `POST /api/files` with headers:
     - `X-File-Name: <sanitized_basename>`
     - `X-SHA256: <hex_digest>`
     - `Content-Length: <size_bytes>`
     - `Authorization: Bearer <AUTH_TOKEN>`
   - The file is read and streamed directly across the HTTP connection in chunks.
3. **Server-Side Pass-Through Hashing:**
   - The Express server intercepts the incoming raw binary stream.
   - It pipelines the stream simultaneously into:
     - A Node.js `crypto.createHash('sha256')` instance.
     - An `@aws-sdk/client-s3` `Upload` / `PutObjectCommand` stream targeting the remote S3 bucket.
4. **Validation and Atomic Database Commit:**
   - Once the stream finishes, the server checks:
     - Does computed `receivedBytes == declaredLength`?
     - Does computed `sha256Hex == declaredSha256`?
   - **On Mismatch:** The server issues an immediate `DeleteObjectCommand` to purge the corrupted object from S3 and returns HTTP 400 (`Checksum or size mismatch`). The database is untouched.
   - **On Match:** The server executes an atomic SQL upsert into Neon PostgreSQL:
     ```sql
     INSERT INTO file_metadata (name, size_bytes, sha256, stored_path, created_at)
     VALUES ($1, $2, $3, $4, NOW())
     ON CONFLICT (name) DO UPDATE SET
       size_bytes = EXCLUDED.size_bytes,
       sha256 = EXCLUDED.sha256,
       stored_path = EXCLUDED.stored_path,
       created_at = NOW();
     ```
   - No corrupted or incomplete file can ever appear in `neoshell list`.

### 5.3 The Download Verification Pipeline
1. Client requests `GET /api/files/:name`.
2. Server validates authorization, checks PostgreSQL metadata, and streams the S3 object using `GetObjectCommand`, sending `Content-Length` and `X-SHA256` headers.
3. Client streams incoming bytes directly into a temporary file (`<target>.part`).
4. While writing, the client computes the running SHA-256 digest.
5. Once complete, the client compares the computed hash against `X-SHA256`.
6. If the checksum matches, `os.replace()` atomically renames `<target>.part` to `<target>`. If a mismatch occurs, the `.part` file is deleted and an error is raised.

### 5.4 Temporary Sharing via Presigned URLs
1. User runs `neoshell share <filename> --expires 24h [--clip]`.
2. Client converts duration string (`1h`, `24h`, `7d`) to seconds and calls `POST /api/files/:name/share`.
3. Server validates authorization, confirms file existence in PostgreSQL, clamps expiration to between 60 seconds and 604,800 seconds (7 days, Backblaze B2 limit), and signs an S3 `GetObjectCommand` using `@aws-sdk/s3-request-presigner`.
4. Server returns `{ "ok": true, "url": "https://...", "expires_at": "..." }`.
5. The CLI prints the URL, and if `--clip` is supplied, copies it directly to the system clipboard using the platform utility (`clip` on Windows, `pbcopy` on macOS, `wl-copy`/`xclip` on Linux).

### 5.5 Configuration Resolution Hierarchy
The Neoshell client determines server URL and auth credentials via a strict 4-tier precedence hierarchy implemented in `client/src/neoshell/config.py`:

```
+-------------------------------------------------------------+
|               CONFIGURATION PRECEDENCE RESOLUTION           |
+-------------------------------------------------------------+
|                                                             |
|  1. CLI Flags:                                              |
|     neoshell --url <url> --token <token> ...                |
|                                                             |
|  2. Process Environment Variables:                          |
|     NEOSHELL_URL / NEOSHELL_TOKEN                           |
|     (Legacy fallback: SERVER_URL / AUTH_TOKEN)              |
|                                                             |
|  3. Saved Persistent TOML File:                             |
|     Linux:   ~/.config/neoshell/config.toml                 |
|     macOS:   ~/Library/Application Support/neoshell/config  |
|     Windows: %APPDATA%\neoshell\config.toml                 |
|                                                             |
|  4. Default Fallback:                                       |
|     http://127.0.0.1:8080 (Token: None)                     |
+-------------------------------------------------------------+
```

Configuration files are saved atomically (writing to `<filename>.tmp` before replacing) with POSIX mode `0600` (read/write restricted to the owner) to safeguard bearer authentication tokens.

---

## 6. Key Engineering Challenges, Pitfalls & Solutions

Throughout the project, several subtle engineering hurdles were identified and resolved:

### 1. Zero-VM Serverless Compatibility
- **Hurdle:** Deploying on platforms like Koyeb or Render assigns dynamic ports via the `PORT` environment variable and imposes strict HTTP health checks. Earlier Dockerfiles attempted to bind to fixed ports.
- **Solution:** `server/src/index.js` was modified to prioritize `process.env.PORT || 8080`, allowing the platform to dictate port binding. The `/health` endpoint was left intentionally unauthenticated so platform health checks succeed without needing credentials.

### 2. S3 Mocking Instability in Continuous Integration
- **Hurdle:** When testing S3 integration in GitHub Actions, MinIO was initially employed. However, MinIO frequently failed in CI due to startup race conditions where the server process started before MinIO finished initializing the target bucket (`ci-neoshell`), causing random test run failures (`275aabc`).
- **Solution:** Commit `8c7ab15` replaced MinIO with `adobe/s3mock:latest`. With Adobe S3Mock, buckets can be pre-declared at container spin-up via `-e initialBuckets=ci-neoshell`. A Python polling probe was integrated into the workflow to guarantee readiness before starting the API server.

### 3. Docker Non-Root Security vs. Volume Ownership
- **Hurdle:** Standard Docker images default to `root`. Running production services as `root` is a security anti-pattern. When switching to user `node` (`98b1f39`), mounted file volumes created by root on host machines caused `EACCES: permission denied` write crashes.
- **Solution:** Added explicit volume chown steps in `docker-compose.yml` and transitioned away from persistent volume writes altogether during the S3 migration, completely side-stepping container filesystem permission hazards.

### 4. PyPI Package Name Collision
- **Hurdle:** The package was intended to be named `neoshell`. However, a package named `neoshell` had already been registered years prior on PyPI by an unrelated terminal shell project.
- **Solution:** Documented in `docs/CLI_PACKAGE_PLAN.md`. The distribution package was cleanly decoupled from the command entry point:
  - Distribution name: **`neoshell-cli`**
  - Console script entry point: **`neoshell`** (`neoshell.cli:main`)
  This preserved the clean, concise `neoshell` terminal command while publishing safely under an uncontested PyPI name.

### 5. Safe Express Body Parsing for Binary Streams
- **Hurdle:** Standard Express middleware like `bodyParser.json()` or `express.raw()` buffers entire request bodies in memory. Placing `express.json()` at the root app level would consume streaming uploads, breaking performance for large files.
- **Solution:** Global body parsers were omitted. `express.json()` was scoped strictly to endpoints that consume JSON (such as `POST /api/files/:name/share`), while `POST /api/files` received raw, untampered request streams directly piped to S3.

---

## 7. Quality Assurance, Testing Matrix & Verification

### 7.1 Automated Test Suite
The codebase includes 35 comprehensive automated tests across three core test suites in `tests/`:

1. **`test_config.py` (11 tests):**
   - Validates configuration directory overrides via `NEOSHELL_CONFIG_DIR`.
   - Validates atomic save, partial update, and clear operations.
   - Verifies the complete 4-tier precedence order.
   - Verifies absence of leftover temporary files and enforces POSIX `0600` permission masks.
2. **`test_api.py` (9 tests):**
   - Validates file SHA-256 calculation.
   - Validates bearer token authentication headers.
   - Tests error mapping for HTTP 401 (suggests `neoshell login`), 404, connection timeouts (explaining PaaS cold starts), and connection refused.
   - Simulates transmission corruption and validates `ChecksumMismatchError` handling.
   - Tests presigned share response parsing.
3. **`test_cli.py` (15 tests):**
   - Tests Typer CLI commands using Click/Typer `CliRunner`.
   - Validates `--help`, `--version`, `login`, `logout`, `status`, `list`, `upload`, `download`, `share`, `delete`, and `info`.
   - Validates duration string parsing (`1h`, `24h`, `7d`) and human-readable size formatting (B, KB, MB, GB).

**Local Verification Execution:**
```bash
pytest tests -v
# Output: 34 passed, 1 skipped (POSIX permissions on Windows) in 0.78s
```

### 7.2 GitHub Actions CI Matrix
The GitHub Actions pipeline (`.github/workflows/integrate.yml`) executes on every push and pull request to `main`:
- **Python Client Matrix:** Runs across **Ubuntu**, **Windows**, and **macOS** on **Python 3.9** and **Python 3.12**.
  - Runs full unit and CLI test suites.
  - Builds package wheels and source distributions (`python -m build client`).
  - Verifies CLI entry points (`neoshell`, `python -m neoshell`, `python client/main.py`).
- **Node.js Server:** Checks syntax and dependencies (`node --check server/src/index.js`).
- **Integration Smoke Job:**
  - Spins up Docker services: PostgreSQL 16 and Adobe S3Mock.
  - Launches live Express API server.
  - Executes `scripts/smoke_test.py`.
  - Executes full CLI user journey: `neoshell login` -> `status` -> `upload` -> `list` -> `download` -> `diff` -> `share` -> `delete`.

### 7.3 Automated Release Pipeline
The release workflow (`.github/workflows/release.yml`) executes on `v*` git tags or manual triggers:
- Verifies that the git tag version strictly matches `client/pyproject.toml`.
- Runs tests and builds wheel/sdist packages.
- Validates package metadata using `twine check`.
- Publishes distributions directly to PyPI via OpenID Connect (OIDC) Trusted Publishing (`pypa/gh-action-pypi-publish`), removing the need for long-lived API tokens or passwords stored in repository secrets.

---

## 8. Deployment Topologies

Neoshell supports three primary deployment models:

| Topology | Best For | Architecture | Cost |
| :--- | :--- | :--- | :--- |
| **Zero-VM Cloud** | Production / Remote Access | Koyeb or Render Web Service + Neon PostgreSQL + Backblaze B2 or Cloudflare R2 | $0.00 / Free Tier |
| **Cloudflare Tunnel** | Team / Home Lab | Local Docker container on laptop/desktop + Cloudflare Tunnel (`cloudflared`) + Neon + B2/R2 | $0.00 |
| **Local Offline** | Development / Air-Gapped | Docker Compose (Server + PostgreSQL + MinIO) on `127.0.0.1:8080` | $0.00 |

---

## 9. Current Limitations & Future Roadmap

While Neoshell v0.1.0 provides a complete, robust personal cloud file manager, several strategic enhancements are identified for future releases:

1. **Database-Backed Revocable Share Links:**
   - *Current Limitation:* Share URLs are standard presigned S3 URLs that cannot be revoked prior to their natural expiration.
   - *Roadmap:* Implement short redirect URLs (`GET /s/:id`) resolved against PostgreSQL, allowing instantaneous revocation.
2. **Multi-User Role-Based Access Control (RBAC):**
   - *Current Limitation:* A single shared `AUTH_TOKEN` grants full read/write access to all files.
   - *Roadmap:* User accounts, JWT authentication, and per-user storage quotas and file ownership.
3. **Multipart & Resumable Transfers:**
   - *Current Limitation:* Files are uploaded in a single HTTP request body; interrupted uploads must restart from 0%.
   - *Roadmap:* Implement S3 multipart upload protocol with chunked hashing and client-side resume capabilities.
4. **Client-Side Encryption (E2EE):**
   - *Roadmap:* Optional AES-GCM client-side encryption before byte upload so object storage providers cannot read file contents.

---

## 10. Conclusion

From its origins as an experimental raw TCP socket experiment to a fully packaged, PyPI-distributed CLI backed by serverless cloud infrastructure, Neoshell demonstrates disciplined full-stack architecture and lifecycle engineering. By combining cryptographic integrity verification, clean CLI ergonomics, and zero-VM cloud services, Neoshell delivers a durable, self-owned file manager built for the modern command line.
