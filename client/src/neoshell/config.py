"""Configuration management and persistence for Neoshell CLI."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import platformdirs

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_SERVER_URL = "http://127.0.0.1:8080"


@dataclass
class Config:
    url: str
    token: Optional[str] = None


def get_config_dir() -> Path:
    """Return the configuration directory path, checking NEOSHELL_CONFIG_DIR first."""
    override = os.getenv("NEOSHELL_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("neoshell", appauthor=False))


def get_config_file_path() -> Path:
    """Return the path to the config.toml file."""
    return get_config_dir() / "config.toml"


def load_saved_config() -> dict[str, Optional[str]]:
    """Read saved config from config.toml if present.
    
    Supports both [neoshell] table and top-level keys.
    """
    path = get_config_file_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        section = data.get("neoshell", {})
        url = section.get("url") or data.get("url")
        token = section.get("token") or data.get("token")
        result: dict[str, Optional[str]] = {"url": None, "token": None}
        if url:
            result["url"] = str(url).rstrip("/")
        if token:
            result["token"] = str(token)
        return result
    except Exception:
        return {"url": None, "token": None}


def resolve_config(
    cli_url: Optional[str] = None,
    cli_token: Optional[str] = None,
) -> Config:
    """Resolve Config adhering to strict precedence:
    1. CLI flags (--url, --token)
    2. Environment: NEOSHELL_URL / NEOSHELL_TOKEN, then legacy SERVER_URL / AUTH_TOKEN
    3. Saved config file
    4. Default http://127.0.0.1:8080 (URL only)
    """
    # 1. Resolve URL
    resolved_url: Optional[str] = None
    if cli_url:
        resolved_url = cli_url.strip().rstrip("/")
    elif os.getenv("NEOSHELL_URL"):
        resolved_url = os.environ["NEOSHELL_URL"].strip().rstrip("/")
    elif os.getenv("SERVER_URL"):
        resolved_url = os.environ["SERVER_URL"].strip().rstrip("/")
    else:
        saved = load_saved_config()
        if saved.get("url"):
            resolved_url = saved["url"]
        else:
            resolved_url = DEFAULT_SERVER_URL

    # 2. Resolve Token
    resolved_token: Optional[str] = None
    if cli_token is not None:
        resolved_token = cli_token.strip() or None
    elif os.getenv("NEOSHELL_TOKEN") is not None:
        resolved_token = os.environ["NEOSHELL_TOKEN"].strip() or None
    elif os.getenv("AUTH_TOKEN") is not None:
        resolved_token = os.environ["AUTH_TOKEN"].strip() or None
    else:
        saved = load_saved_config()
        if saved.get("token"):
            resolved_token = saved["token"]

    return Config(url=resolved_url, token=resolved_token)


def save_config(url: Optional[str] = None, token: Optional[str] = None) -> Path:
    """Atomically write configuration to config.toml.
    
    If url or token is None, retains existing value from file if present.
    Ensures directory exists and sets 0600 permissions on POSIX.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    target_path = get_config_file_path()

    current = load_saved_config()
    final_url = url.rstrip("/") if url is not None else current.get("url")
    final_token = token if token is not None else current.get("token")

    lines = ["[neoshell]"]
    if final_url:
        lines.append(f'url = "{final_url}"')
    if final_token:
        lines.append(f'token = "{final_token}"')
    lines.append("")
    content = "\n".join(lines).encode("utf-8")

    # Atomic write via temp file in the same directory
    temp_fd, temp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=str(config_dir))
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        if hasattr(os, "chmod") and os.name != "nt":
            os.chmod(temp_path, 0o600)

        os.replace(temp_path, target_path)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise

    return target_path


def clear_saved_token() -> bool:
    """Remove saved token while keeping saved URL if present."""
    path = get_config_file_path()
    if not path.is_file():
        return False
    current = load_saved_config()
    if not current.get("token"):
        return False
    save_config(url=current.get("url"), token="")
    return True


def clear_config() -> bool:
    """Delete config file."""
    path = get_config_file_path()
    if path.is_file():
        path.unlink()
        return True
    return False
