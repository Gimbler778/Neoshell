# Neoshell CLI Distribution — No Git Clone Needed

> **Superseded:** see [CLI_PACKAGE_PLAN.md](CLI_PACKAGE_PLAN.md) for the current plan.

## Problem

Today users must use the CLI like this:

```bash
git clone https://github.com/<you>/Neoshell.git
pip install -r client/requirements.txt
python client/main.py list --url https://YOUR-APP.example.com --token YOUR_AUTH_TOKEN
```

That clones the full platform (server + DB + infra + client) just to upload a file.
It also forces `--url` / `--token` on every command and breaks on Windows/macOS/Linux differences.

This is dev usage, not end-user distribution.

## Decision

- Server model: **central hosted** — you host one server (Koyeb/Render + Neon + B2/R2).
- Users only install the CLI and point to your URL.
- Target OS: **Linux + Windows + macOS**.
- Install method: **`pip` / `pipx` from PyPI** (no clone, no Docker, no Python path hacks).

## Target UX

```bash
# once
pipx install neoshell
# or: pip install --user neoshell

# once per machine
neoshell login --url https://YOUR-APP.koyeb.app --token <user-token>

# daily use
neoshell list
neoshell upload ./photo.zip
neoshell delete photo.zip
neoshell status
neoshell logout
```

Config precedence:

1. `--url` / `--token` flags (override)
2. `SERVER_URL` / `AUTH_TOKEN` env vars
3. Saved config file
4. Default `http://127.0.0.1:8080` (local dev only)

Saved config location (via `platformdirs`):

- Linux: `~/.config/neoshell/config.toml`
- macOS: `~/Library/Application Support/neoshell/config.toml`
- Windows: `%APPDATA%\neoshell\config.toml`

## What Needs To Change

Current code: `client/main.py`, `client/requirements.txt`, `client/Dockerfile` — script-only, no packaging.

Needed:

1. `client/pyproject.toml` with `[project] name = "neoshell"` and `[project.scripts] neoshell = "neoshell.cli:app"`.
2. Restructure to `client/src/neoshell/cli.py`, `config.py`, `api.py` (move from `client/main.py`).
3. Add `login/logout/status` commands to persist URL + token.
4. Publish to PyPI on `v*` git tag via GitHub Actions Trusted Publishing.
5. Keep `docker compose run client` and `python client/main.py` only for local dev / self-host.

## End-User Install (after PyPI release)

```bash
pipx install neoshell
neoshell login --url https://YOUR-APP.koyeb.app --token PASTE_TOKEN_HERE
neoshell list
```

Update token:

```bash
neoshell login --token NEW_TOKEN
```

No repo clone, no `requirements.txt`, no `python client/main.py`.

## Dev / Self-Host Install (unchanged)

```bash
git clone <repo>
cp .env.example .env
docker compose up --build -d server
pip install -r client/requirements.txt
python client/main.py list --host 127.0.0.1 --port 8080 --token $AUTH_TOKEN
```

## Notes / Limits

- Central server currently uses single shared `AUTH_TOKEN`. OK for private MVP, needs per-user auth for public multi-user.
- Package name `neoshell` must be checked on PyPI, fallback `neoshell-cloud` if taken.
- Later options (not now): single `.exe` via PyInstaller, `brew install`, Docker Hub `neoshell-cli` image.
- Free hosts sleep — first CLI call after idle may take 20-50s (cold start).

## Next Steps

1. Add packaging + config persistence.
2. Test `pip install ./client` on Linux/Windows/macOS.
3. Tag `v0.1.0` -> PyPI -> update `README.md` + `docs/DEPLOYMENT_NO_VM.md` with `pipx install` instructions.
