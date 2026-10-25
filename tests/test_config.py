"""Unit tests for neoshell.config."""

import os
from pathlib import Path

import pytest

from neoshell.config import (
    DEFAULT_SERVER_URL,
    clear_config,
    clear_saved_token,
    get_config_dir,
    get_config_file_path,
    load_saved_config,
    resolve_config,
    save_config,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Ensure every test runs with an isolated config directory and clean env."""
    config_dir = tmp_path / "neoshell_config"
    monkeypatch.setenv("NEOSHELL_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("NEOSHELL_URL", raising=False)
    monkeypatch.delenv("NEOSHELL_TOKEN", raising=False)
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    return config_dir


def test_config_dir_override(isolated_config):
    """Verify NEOSHELL_CONFIG_DIR redirects config path."""
    assert get_config_dir() == isolated_config
    assert get_config_file_path() == isolated_config / "config.toml"


def test_save_and_load_config():
    """Verify saving configuration creates file and loading retrieves values."""
    save_config(url="https://cloud.example.com", token="secret-123")
    loaded = load_saved_config()
    assert loaded["url"] == "https://cloud.example.com"
    assert loaded["token"] == "secret-123"


def test_save_config_partial_update():
    """Verify partial updates retain existing configuration."""
    save_config(url="https://initial.example.com", token="initial-token")
    # Update only token
    save_config(token="new-token")
    loaded = load_saved_config()
    assert loaded["url"] == "https://initial.example.com"
    assert loaded["token"] == "new-token"

    # Update only url
    save_config(url="https://updated.example.com")
    loaded = load_saved_config()
    assert loaded["url"] == "https://updated.example.com"
    assert loaded["token"] == "new-token"


def test_clear_saved_token_and_config():
    """Verify clearing token and removing config file."""
    save_config(url="https://example.com", token="abc")
    assert clear_saved_token() is True
    loaded = load_saved_config()
    assert loaded["token"] is None or loaded["token"] == ""
    assert loaded["url"] == "https://example.com"

    assert clear_config() is True
    assert not get_config_file_path().exists()


def test_precedence_cli_overrides_everything(monkeypatch):
    """CLI options must have the highest precedence."""
    save_config(url="https://saved.example.com", token="saved-token")
    monkeypatch.setenv("NEOSHELL_URL", "https://env.example.com")
    monkeypatch.setenv("NEOSHELL_TOKEN", "env-token")

    cfg = resolve_config(cli_url="https://cli.example.com", cli_token="cli-token")
    assert cfg.url == "https://cli.example.com"
    assert cfg.token == "cli-token"


def test_precedence_env_overrides_saved(monkeypatch):
    """Environment variables take precedence over saved config."""
    save_config(url="https://saved.example.com", token="saved-token")
    monkeypatch.setenv("NEOSHELL_URL", "https://env.example.com")
    monkeypatch.setenv("NEOSHELL_TOKEN", "env-token")

    cfg = resolve_config()
    assert cfg.url == "https://env.example.com"
    assert cfg.token == "env-token"


def test_precedence_legacy_env(monkeypatch):
    """Legacy SERVER_URL and AUTH_TOKEN are used if NEOSHELL_* are not set."""
    save_config(url="https://saved.example.com", token="saved-token")
    monkeypatch.setenv("SERVER_URL", "https://legacy.example.com")
    monkeypatch.setenv("AUTH_TOKEN", "legacy-token")

    cfg = resolve_config()
    assert cfg.url == "https://legacy.example.com"
    assert cfg.token == "legacy-token"


def test_precedence_saved_config_over_default():
    """Saved config is used when no CLI flags or env vars are set."""
    save_config(url="https://saved.example.com", token="saved-token")
    cfg = resolve_config()
    assert cfg.url == "https://saved.example.com"
    assert cfg.token == "saved-token"


def test_precedence_default_when_empty():
    """Default local URL is used when no config exists."""
    cfg = resolve_config()
    assert cfg.url == DEFAULT_SERVER_URL
    assert cfg.token is None


def test_atomic_write_no_leftover_tmp():
    """Verify atomic write creates the file without leaving temporary files behind."""
    save_config(url="https://test.example.com", token="token")
    files = list(get_config_dir().iterdir())
    assert len(files) == 1
    assert files[0].name == "config.toml"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions test")
def test_posix_permissions(tmp_path):
    """On POSIX systems, config.toml permissions should be 0600."""
    save_config(url="https://secure.example.com", token="secret")
    mode = get_config_file_path().stat().st_mode & 0o777
    assert mode == 0o600
