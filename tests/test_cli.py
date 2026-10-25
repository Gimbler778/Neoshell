"""Unit and integration tests for neoshell.cli using Typer CliRunner."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from neoshell.cli import app, reset_state
from neoshell.formatting import format_size, parse_duration_to_seconds

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Ensure every CLI test runs with isolated config."""
    reset_state()
    config_dir = tmp_path / "neoshell_config"
    monkeypatch.setenv("NEOSHELL_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("NEOSHELL_URL", raising=False)
    monkeypatch.delenv("NEOSHELL_TOKEN", raising=False)
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    return config_dir


def test_formatting_duration_parsing():
    assert parse_duration_to_seconds("60s") == 60
    assert parse_duration_to_seconds("30m") == 1800
    assert parse_duration_to_seconds("1h") == 3600
    assert parse_duration_to_seconds("24h") == 86400
    assert parse_duration_to_seconds("7d") == 604800
    assert parse_duration_to_seconds("300") == 300

    with pytest.raises(ValueError):
        parse_duration_to_seconds("invalid")


def test_formatting_format_size():
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KiB"
    assert format_size(1024 * 1024) == "1.0 MiB"


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Neoshell" in result.output
    assert "login" in result.output
    assert "upload" in result.output
    assert "download" in result.output
    assert "share" in result.output


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "neoshell-cli v0.1.0" in result.output


@patch("neoshell.api.ApiClient.health")
def test_cli_login_success(mock_health):
    mock_health.return_value = {"ok": True}
    result = runner.invoke(app, ["login", "--url", "https://app.example.com", "--token", "tok-123"])
    assert result.exit_code == 0
    assert "Successfully configured Neoshell" in result.output


@patch("neoshell.api.ApiClient.health")
def test_cli_login_failure_unreachable(mock_health):
    mock_health.side_effect = Exception("Connection refused")
    result = runner.invoke(app, ["login", "--url", "http://127.0.0.1:9999"])
    assert result.exit_code == 1
    assert "Connection refused" in result.output or "Error" in result.output


@patch("neoshell.api.ApiClient.health")
@patch("neoshell.api.ApiClient.list_files")
def test_cli_status(mock_list, mock_health):
    mock_health.return_value = {"ok": True}
    mock_list.return_value = [{"name": "file.txt"}]

    result = runner.invoke(app, ["status", "--url", "http://127.0.0.1:8080"])
    assert result.exit_code == 0
    assert "Online" in result.output

    # JSON mode
    json_result = runner.invoke(app, ["--json", "status", "--url", "http://127.0.0.1:8080"])
    assert json_result.exit_code == 0
    data = json.loads(json_result.output)
    assert data["ok"] is True
    assert data["healthy"] is True
    assert data["file_count"] == 1


@patch("neoshell.api.ApiClient.list_files")
def test_cli_list(mock_list):
    mock_list.return_value = [
        {
            "name": "photo.jpg",
            "size_bytes": 1024,
            "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "created_at": "2026-10-25T12:00:00Z",
        }
    ]

    result = runner.invoke(app, ["list", "--url", "http://127.0.0.1:8080"])
    assert result.exit_code == 0
    assert "photo.jpg" in result.output

    # JSON mode
    json_result = runner.invoke(app, ["--json", "list", "--url", "http://127.0.0.1:8080"])
    assert json_result.exit_code == 0
    data = json.loads(json_result.output)
    assert len(data) == 1
    assert data[0]["name"] == "photo.jpg"


@patch("neoshell.api.ApiClient.upload_file")
def test_cli_upload(mock_upload, tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_text("file 1")
    f2 = tmp_path / "f2.txt"
    f2.write_text("file 2")

    mock_upload.side_effect = lambda path, **kwargs: {"ok": True, "file": {"name": path.name}}

    result = runner.invoke(app, ["upload", str(f1), str(f2)])
    assert result.exit_code == 0
    assert "f1.txt" in result.output
    assert "f2.txt" in result.output


def test_cli_upload_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.txt"
    result = runner.invoke(app, ["upload", str(missing)])
    assert result.exit_code == 1
    assert "File not found" in result.output


@patch("neoshell.api.ApiClient.download_file")
@patch("neoshell.api.ApiClient.get_file_info")
def test_cli_download(mock_info, mock_download, tmp_path):
    mock_info.return_value = {"name": "test.txt", "size_bytes": 12}
    dest = tmp_path / "out.txt"
    mock_download.return_value = dest

    result = runner.invoke(app, ["download", "test.txt", "-o", str(dest)])
    assert result.exit_code == 0
    assert "Downloaded:" in result.output


@patch("neoshell.api.ApiClient.share_file")
def test_cli_share(mock_share):
    mock_share.return_value = {
        "ok": True,
        "url": "https://s3.example.com/share-url",
        "expires_at": "2026-10-26T12:00:00Z",
    }

    result = runner.invoke(app, ["share", "photo.jpg", "--expires", "24h"])
    assert result.exit_code == 0
    assert "https://s3.example.com/share-url" in result.output


@patch("neoshell.api.ApiClient.delete_file")
def test_cli_delete_with_yes(mock_delete):
    mock_delete.return_value = {"ok": True, "message": "Deleted photo.jpg"}

    result = runner.invoke(app, ["delete", "photo.jpg", "--yes"])
    assert result.exit_code == 0
    assert "Deleted photo.jpg" in result.output


@patch("neoshell.api.ApiClient.get_file_info")
def test_cli_info(mock_info):
    mock_info.return_value = {
        "name": "photo.jpg",
        "size_bytes": 2048,
        "sha256": "1234567890abcdef",
        "created_at": "2026-10-25T12:00:00Z",
    }

    result = runner.invoke(app, ["info", "photo.jpg"])
    assert result.exit_code == 0
    assert "photo.jpg" in result.output
    assert "2048" in result.output or "2.0 KiB" in result.output


def test_cli_logout():
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower() or "no saved token" in result.output.lower()
