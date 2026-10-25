# Neoshell CLI Package Plan

Turn Neoshell into a package users can install with a single command, then use entirely from the terminal for file sharing.

This supersedes the packaging sketch in `docs/CLI_DISTRIBUTION.md` and records the decisions taken since.

## Goal

```bash
pipx install neoshell-cli        # once (PyPI)
neoshell login --url https://YOUR-APP.koyeb.app --token TOKEN
neoshell upload ./photo.zip ./notes.txt
neoshell list
neoshell download photo.zip
neoshell share photo.zip --expires 24h
neoshell delete photo.zip
neoshell status
neoshell logout
```

No git clone, no Docker, no `python client/main.py`, no `--url`/`--token` on every command.

## Decisions

| Question | Decision | Reason |
| --- | --- | --- |
| Install ecosystem | Python, `pipx`/`pip` | Reuses the existing Python client. Works on Windows, macOS, Linux. |
| Distribution name | `neoshell-cli` | `neoshell` on PyPI is already taken by an unrelated shell project. Verified free. |
| Command name | `neoshell` | Entry point names are independent of distribution names. |
| Server model | Central hosted server | Users only install the client and point it at your URL. |
| Sharing scope | Download + share links in v0.1.0 | Upload/list/delete alone is not "sharing". |
| Config storage | Plain TOML at 0600 | No extra dependency. Structured so `keyring` can be added later. |

Config precedence, highest first:

1. `--url` / `--token` flags
2. Environment: `NEOSHELL_URL` / `NEOSHELL_TOKEN`, then legacy `SERVER_URL` / `AUTH_TOKEN`
3. Saved config file
4. `http://127.0.0.1:8080` (local dev only)

Saved config location via `platformdirs.user_config_dir("neoshell")`:

- Linux: `~/.config/neoshell/config.toml`
- macOS: `~/Library/Application Support/neoshell/config.toml`
- Windows: `%APPDATA%\neoshell\config.toml`

## Current State

| Component | Location | Status |
| --- | --- | --- |
| CLI | `client/main.py` | Single script. No packaging, no config persistence. |
| Server | `server/src/index.js` | Express + PostgreSQL + S3. List/upload/delete only. |
| Download endpoint | — | Missing. |
| Share links | — | Missing. |
| Release automation | `.github/workflows/integrate.yml` | CI only, no publishing. |

## Phase 1 — Packaging and Parity

No server changes. The existing commands keep working, just installable.

### New layout

```text
client/
  pyproject.toml
  src/neoshell/__init__.py
  src/neoshell/__main__.py      # python -m neoshell
  src/neoshell/cli.py           # typer app + main()
  src/neoshell/config.py        # load/save, precedence, atomic write
  src/neoshell/api.py           # ApiClient
  src/neoshell/formatting.py    # tables, progress, duration/size parsing
  main.py                       # thin shim -> neoshell.cli.main (dev compat)
  Dockerfile                    # pip install . ; ENTRYPOINT ["neoshell"]
```

`client/requirements.txt` is removed. The Dockerfile, CI, and docs switch to `pip install ./client`.

### `pyproject.toml`

- Build backend: `hatchling`
- Name `neoshell-cli`, version `0.1.0`, `requires-python = ">=3.9"`
- Dependencies: `typer`, `rich`, `requests`, `platformdirs`, `tomli` for Python < 3.11
- `[project.scripts] neoshell = "neoshell.cli:main"`
- Optional `dev` extra with `pytest` and `build`

### Config module

- `Config(url, token)` dataclass.
- `NEOSHELL_CONFIG_DIR` environment override so tests can redirect the path.
- Atomic write: write a temp file, then `os.replace`.
- `chmod 0600` on POSIX; Windows relies on the user profile ACL.
- Token is stored in plaintext. Documented as a limitation, not silently ignored.

### CLI behaviour

- Global `--url`, `--token`, `--json`, `--quiet`, `--timeout` through a Typer callback.
- `login` calls `/health` and refuses to save an unreachable or wrong URL. `--token` alone updates only the token.
- `status` prints URL, whether a token is stored, health result, and file count.
- `upload` accepts multiple paths, shows a progress bar, continues past failures, and exits non-zero if any file failed.
- `delete` accepts multiple names and `--yes` to skip confirmation.
- `list` gains `--json` for scripting.
- Error mapping: `401` suggests `neoshell login`, connection refused suggests local dev, timeout mentions free-host cold starts.
- Exit codes: `0` success, `1` runtime failure, `2` usage error.

### Compatibility

- `client/main.py` stays as a shim so `python client/main.py ...` works after `pip install -e ./client`.
- `docker compose run --rm client upload sample.txt` keeps working via the new entry point.

## Phase 2 — Download and Share

### Server changes (`server/src/index.js`)

1. `GET /api/files/:name`
   - `GetObjectCommand`, pipe `Body` to the response.
   - Sets `Content-Length`, `Content-Disposition: attachment`, and `X-SHA256`.
   - Auth required. `NoSuchKey` returns 404.
   - Proxy rather than redirect, so private buckets work and `AUTH_TOKEN` stays meaningful.
2. `POST /api/files/:name/share`
   - New dependency `@aws-sdk/s3-request-presigner`.
   - Body `{ "expires_in": 3600 }`, response `{ ok, url, expires_at }`.
   - Clamp to 60 seconds through 7 days. Backblaze B2 caps presigned URL lifetime at 7 days.
   - `express.json()` mounted only on this route so the raw streaming upload path is untouched.
   - Reuses `sanitizeFilename`.

### CLI changes

- `download NAME [-o PATH]` streams to `.part`, verifies SHA-256 from `X-SHA256`, then renames atomically.
- `share NAME [--expires 1h|24h|7d] [--clip]` prints the URL and expiry. `--clip` copies using `clip` (Windows), `pbcopy` (macOS), or `wl-copy`/`xclip` (Linux).
- `info NAME` shows metadata without downloading.

## Phase 3 — Tests, Release, Docs

### Tests

- `tests/test_config.py`: precedence order, atomic write, permissions, `NEOSHELL_CONFIG_DIR`.
- `tests/test_api.py`: download checksum mismatch, expired/invalid share responses, error mapping.
- `tests/test_cli.py`: `CliRunner` against a faked HTTP layer.
- Integration: extend the existing MinIO-backed CI job to fetch a presigned URL and download a file end to end.

### CI and release

- CI matrix: Python 3.9 and 3.12 on ubuntu, windows, macos.
- Add `python -m build` and `twine check`.
- `.github/workflows/release.yml` triggered on `v*` tags:
  - Fail if the tag does not match the version in `pyproject.toml`.
  - Run tests, build, publish with `pypa/gh-action-pypi-publish`.
  - Trusted Publishing with `permissions: id-token: write` and the `pypi` environment.
- Optional TestPyPI dry run behind `workflow_dispatch`.

### Docs

- `README.md`: quick start becomes `pipx install neoshell-cli` plus `neoshell login`.
- `docs/DEPLOYMENT_NO_VM.md`: replace `python client/main.py` instructions.
- New `docs/CLI.md`: full command reference.
- Mark `docs/CLI_DISTRIBUTION.md` as superseded by this document.

## Manual Steps (Repository Owner)

1. Create the PyPI project `neoshell-cli` and add a pending Trusted Publisher for this repository, workflow `release.yml`, environment `pypi`.
2. Push a `v0.1.0` tag to trigger the first publish.
3. Optionally repeat the setup on TestPyPI.

## Known Limitations

- The `neoshell` command name collides with the unrelated `NeoShell` shell package. Distribution names differ, so PyPI is unaffected, but pipx users cannot have both installed.
- Share links are presigned S3 URLs. They bypass `AUTH_TOKEN` for their lifetime and cannot be revoked individually. Revocable links require DB-backed share tokens, a later phase.
- A single shared `AUTH_TOKEN` means anyone holding it can see every file. Acceptable for a personal or team MVP; real multi-user sharing needs per-user auth.
- Uploads are one POST per file, so host body-size limits still apply.
- No resume for interrupted transfers.

## Commit Boundaries

1. `client`: package skeleton, config, login/status
2. `client`: download and share commands
3. `server`: download and share endpoints
4. `ci`: tests, matrix, release workflow
5. `docs`: README and CLI reference

## Verification Checklist

```bash
# packaging
pip install --upgrade build
python -m build client
twine check client/dist/*
pipx install ./client
neoshell --help

# local server (from repo root)
docker compose up --build -d server
neoshell login --url http://127.0.0.1:8080 --token "$AUTH_TOKEN"
neoshell status
neoshell upload sample.txt
neoshell list
neoshell download sample.txt -o /tmp/sample.txt
neoshell share sample.txt --expires 1h
neoshell delete sample.txt --yes

# python module entry
python -m neoshell --help
```
