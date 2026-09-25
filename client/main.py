import hashlib
import os
from pathlib import Path
from typing import Optional

import requests
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Personal Cloud HTTP File Manager CLI")
console = Console()


def get_server_url(url: Optional[str], host: Optional[str], port: Optional[int]) -> str:
    if url:
        return url.rstrip("/")
    configured_url = os.getenv("SERVER_URL")
    if configured_url:
        return configured_url.rstrip("/")
    resolved_host = host or os.getenv("SERVER_HOST", "127.0.0.1")
    resolved_port = port or int(os.getenv("SERVER_PORT", "8080"))
    return f"http://{resolved_host}:{resolved_port}"


def get_auth_token(token: Optional[str]) -> Optional[str]:
    return token if token is not None else os.getenv("AUTH_TOKEN")


def request_headers(token: Optional[str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def parse_response(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Invalid server response: {response.text}") from exc
    if not response.ok:
        raise RuntimeError(payload.get("error", f"HTTP {response.status_code}"))
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_ok(response: dict) -> None:
    if not response.get("ok"):
        raise typer.BadParameter(response.get("error", "Unknown server error"))


@app.command()
def upload(
    file_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host for local use"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port for local use"),
    token: Optional[str] = typer.Option(None, "--token", help="Shared auth token"),
):
    base_url = get_server_url(url, host, port)
    token = get_auth_token(token)
    checksum = file_sha256(file_path)
    headers = {
        **request_headers(token),
        "X-File-Name": file_path.name,
        "X-SHA256": checksum,
        "Content-Length": str(file_path.stat().st_size),
    }
    with file_path.open("rb") as handle:
        response = parse_response(requests.post(f"{base_url}/api/files", headers=headers, data=handle, timeout=120))
    require_ok(response)
    console.print(f"[green]Uploaded:[/green] {file_path.name}")


@app.command(name="list")
def list_files(
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host for local use"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port for local use"),
    token: Optional[str] = typer.Option(None, "--token", help="Shared auth token"),
):
    response = parse_response(requests.get(
        f"{get_server_url(url, host, port)}/api/files",
        headers=request_headers(get_auth_token(token)),
        timeout=20,
    ))
    require_ok(response)
    table = Table(title="Personal Cloud Files")
    table.add_column("Name", style="cyan")
    table.add_column("Size (bytes)", justify="right")
    table.add_column("SHA256", style="magenta")
    table.add_column("Created At", style="green")
    for item in response.get("files", []):
        table.add_row(str(item.get("name", "")), str(item.get("size_bytes", "")), str(item.get("sha256", "")), str(item.get("created_at", "")))
    console.print(table)


@app.command()
def delete(
    filename: str = typer.Argument(..., help="Remote filename to delete"),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host for local use"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port for local use"),
    token: Optional[str] = typer.Option(None, "--token", help="Shared auth token"),
):
    response = parse_response(requests.delete(
        f"{get_server_url(url, host, port)}/api/files/{requests.utils.quote(filename, safe='')}",
        headers=request_headers(get_auth_token(token)),
        timeout=20,
    ))
    require_ok(response)
    console.print(f"[yellow]{response.get('message', 'Deleted')}[/yellow]")


if __name__ == "__main__":
    app()
