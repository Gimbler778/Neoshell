"""Unit tests for neoshell.api."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from neoshell.api import (
    ApiClient,
    AuthenticationError,
    ChecksumMismatchError,
    ConnectionFailedError,
    NotFoundError,
    ServerError,
    TimeoutError,
    compute_file_sha256,
)


def test_compute_file_sha256(tmp_path):
    sample = tmp_path / "hello.txt"
    sample.write_bytes(b"hello world\n")
    expected = hashlib.sha256(b"hello world\n").hexdigest()
    assert compute_file_sha256(sample) == expected


def test_api_client_headers():
    client_no_token = ApiClient("http://127.0.0.1:8080")
    assert client_no_token.headers == {}

    client_with_token = ApiClient("http://127.0.0.1:8080", token="my-token")
    assert client_with_token.headers == {"Authorization": "Bearer my-token"}


@patch("requests.get")
def test_error_mapping_401(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"ok": False, "error": "Unauthorized"}
    mock_get.return_value = mock_resp

    client = ApiClient("http://127.0.0.1:8080")
    with pytest.raises(AuthenticationError) as exc_info:
        client.list_files()
    assert "login" in str(exc_info.value).lower()


@patch("requests.get")
def test_error_mapping_404(mock_get):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"ok": False, "error": "File not found"}
    mock_get.return_value = mock_resp

    client = ApiClient("http://127.0.0.1:8080")
    with pytest.raises(NotFoundError):
        client.get_file_info("missing.txt")


@patch("requests.get")
def test_error_mapping_connection_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")

    client = ApiClient("http://127.0.0.1:8080")
    with pytest.raises(ConnectionFailedError) as exc_info:
        client.health()
    assert "local development" in str(exc_info.value).lower()


@patch("requests.get")
def test_error_mapping_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout("Timed out")

    client = ApiClient("http://127.0.0.1:8080")
    with pytest.raises(TimeoutError) as exc_info:
        client.health()
    assert "cold starts" in str(exc_info.value).lower()


@patch("requests.get")
def test_download_checksum_mismatch(mock_get, tmp_path):
    content = b"fake payload"
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.headers = {"X-SHA256": "0" * 64}  # mismatching hash
    mock_resp.iter_content.return_value = [content]
    mock_get.return_value = mock_resp

    client = ApiClient("http://127.0.0.1:8080")
    dest = tmp_path / "downloaded.bin"

    with pytest.raises(ChecksumMismatchError):
        client.download_file("file.bin", dest)

    assert not dest.exists()
    assert not (tmp_path / "downloaded.bin.part").exists()


@patch("requests.get")
def test_download_success(mock_get, tmp_path):
    content = b"valid file content"
    correct_sha = hashlib.sha256(content).hexdigest()

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.headers = {"X-SHA256": correct_sha}
    mock_resp.iter_content.return_value = [content]
    mock_get.return_value = mock_resp

    client = ApiClient("http://127.0.0.1:8080")
    dest = tmp_path / "out.txt"

    progress_chunks = []
    saved = client.download_file("out.txt", dest, progress_callback=lambda n: progress_chunks.append(n))

    assert saved == dest
    assert dest.read_bytes() == content
    assert sum(progress_chunks) == len(content)


@patch("requests.post")
def test_share_file_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "ok": True,
        "url": "https://s3.example.com/presigned",
        "expires_at": "2026-10-26T00:00:00Z",
    }
    mock_post.return_value = mock_resp

    client = ApiClient("http://127.0.0.1:8080")
    res = client.share_file("test.txt", expires_in=3600)
    assert res["ok"] is True
    assert res["url"] == "https://s3.example.com/presigned"
