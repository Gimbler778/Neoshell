"""HTTP API client for interacting with Neoshell backend."""

from __future__ import annotations

import hashlib
import io
import os
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

import requests


class NeoshellError(Exception):
    """Base exception for Neoshell errors."""


class AuthenticationError(NeoshellError):
    """Raised when authentication fails (401)."""


class NotFoundError(NeoshellError):
    """Raised when a file or resource is not found (404)."""


class ConnectionFailedError(NeoshellError):
    """Raised when connection to server cannot be established."""


class TimeoutError(NeoshellError):
    """Raised when an HTTP request times out."""


class ChecksumMismatchError(NeoshellError):
    """Raised when verified checksum does not match expected checksum."""


class ServerError(NeoshellError):
    """Raised when the server returns an unexpected error."""


def compute_file_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ProgressReader(io.BufferedReader):
    """Wrapper around raw file reader to report read progress."""

    def __init__(self, raw: io.RawIOBase, callback: Optional[Callable[[int], None]] = None):
        super().__init__(raw)
        self._callback = callback

    def read(self, size: int = -1) -> bytes:
        chunk = super().read(size)
        if chunk and self._callback:
            self._callback(len(chunk))
        return chunk


class ApiClient:
    """Client for Neoshell HTTP API."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_request_error(self, exc: Exception) -> None:
        if isinstance(exc, requests.exceptions.ConnectionError):
            raise ConnectionFailedError(
                f"Could not connect to {self.base_url}. Is the server running? "
                "For local development, verify host and port."
            ) from exc
        if isinstance(exc, requests.exceptions.Timeout):
            raise TimeoutError(
                f"Request to {self.base_url} timed out. "
                "Note: free cloud hosts (Koyeb/Render) can take 20-50s to wake up on cold starts."
            ) from exc
        raise ServerError(str(exc)) from exc

    def _parse_response(self, response: requests.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            if not response.ok:
                if response.status_code == 401:
                    raise AuthenticationError(
                        "Unauthorized (401). Run 'neoshell login --token <token>' to configure authentication."
                    ) from exc
                if response.status_code == 404:
                    raise NotFoundError(f"Resource not found: {response.text}") from exc
                raise ServerError(f"HTTP {response.status_code}: {response.text}") from exc
            raise ServerError(f"Invalid JSON from server: {response.text}") from exc

        if not response.ok:
            error_msg = payload.get("error", f"HTTP {response.status_code}")
            if response.status_code == 401:
                raise AuthenticationError(
                    f"{error_msg} Run 'neoshell login --token <token>' to authenticate."
                )
            if response.status_code == 404:
                raise NotFoundError(error_msg)
            raise ServerError(error_msg)

        return payload

    def health(self) -> dict:
        """Call GET /health."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        except Exception as exc:
            self._handle_request_error(exc)
        return self._parse_response(resp)

    def list_files(self) -> list[dict]:
        """Call GET /api/files."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/files",
                headers=self.headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            self._handle_request_error(exc)
        payload = self._parse_response(resp)
        return payload.get("files", [])

    def get_file_info(self, name: str) -> dict:
        """Fetch metadata for a single file by name."""
        files = self.list_files()
        for f in files:
            if f.get("name") == name:
                return f
        raise NotFoundError(f"File not found: {name}")

    def upload_file(
        self,
        path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Stream file to POST /api/files with SHA-256 and Content-Length."""
        if not path.is_file():
            raise FileNotFoundError(f"Local file does not exist: {path}")

        checksum = compute_file_sha256(path)
        file_size = path.stat().st_size
        req_headers = {
            **self.headers,
            "X-File-Name": path.name,
            "X-SHA256": checksum,
            "Content-Length": str(file_size),
        }

        effective_timeout = timeout or max(self.timeout, 120.0)

        try:
            with open(path, "rb") as raw_file:
                reader = _ProgressReader(raw_file, progress_callback)
                resp = requests.post(
                    f"{self.base_url}/api/files",
                    headers=req_headers,
                    data=reader,
                    timeout=effective_timeout,
                )
        except Exception as exc:
            self._handle_request_error(exc)

        return self._parse_response(resp)

    def download_file(
        self,
        name: str,
        dest_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1024 * 64,
        timeout: Optional[float] = None,
    ) -> Path:
        """Download file from GET /api/files/:name, verify checksum, and atomically save."""
        encoded_name = urllib.parse.quote(name, safe="")
        effective_timeout = timeout or max(self.timeout, 120.0)

        try:
            resp = requests.get(
                f"{self.base_url}/api/files/{encoded_name}",
                headers=self.headers,
                stream=True,
                timeout=effective_timeout,
            )
        except Exception as exc:
            self._handle_request_error(exc)

        if not resp.ok:
            self._parse_response(resp)

        expected_sha = resp.headers.get("X-SHA256", "").strip().lower()

        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_name(f"{dest_path.name}.part")

        digest = hashlib.sha256()
        try:
            with open(part_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        digest.update(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))
        except Exception:
            if part_path.exists():
                part_path.unlink()
            raise

        actual_sha = digest.hexdigest().lower()
        if expected_sha and actual_sha != expected_sha:
            if part_path.exists():
                part_path.unlink()
            raise ChecksumMismatchError(
                f"Checksum mismatch for '{name}'. Expected {expected_sha}, got {actual_sha}."
            )

        # Atomic rename
        os.replace(part_path, dest_path)
        return dest_path

    def share_file(self, name: str, expires_in: int = 86400) -> dict:
        """Request a presigned download link via POST /api/files/:name/share."""
        encoded_name = urllib.parse.quote(name, safe="")
        try:
            resp = requests.post(
                f"{self.base_url}/api/files/{encoded_name}/share",
                headers=self.headers,
                json={"expires_in": expires_in},
                timeout=self.timeout,
            )
        except Exception as exc:
            self._handle_request_error(exc)

        return self._parse_response(resp)

    def delete_file(self, name: str) -> dict:
        """Delete file via DELETE /api/files/:name."""
        encoded_name = urllib.parse.quote(name, safe="")
        try:
            resp = requests.delete(
                f"{self.base_url}/api/files/{encoded_name}",
                headers=self.headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            self._handle_request_error(exc)

        return self._parse_response(resp)
