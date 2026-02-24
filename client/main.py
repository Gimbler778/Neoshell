import hashlib
import json
import os
import socket
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Personal Cloud CLI over custom TCP protocol")
console = Console()


def get_server_config(host: Optional[str], port: Optional[int]) -> tuple[str, int]:
    resolved_host = host or os.getenv("SERVER_HOST", "127.0.0.1")
    resolved_port = port or int(os.getenv("SERVER_PORT", "4000"))
    return resolved_host, resolved_port


def _recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break

    if not data:
        raise RuntimeError("No response from server")

    line = bytes(data).split(b"\n", 1)[0]
    return line.decode("utf-8")


def send_command(
    command_line: str,
    payload: bytes = b"",
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> dict:
    resolved_host, resolved_port = get_server_config(host, port)
    with socket.create_connection((resolved_host, resolved_port), timeout=20) as sock:
        sock.sendall((command_line + "\n").encode("utf-8"))
        if payload:
            sock.sendall(payload)

        response_line = _recv_line(sock)
        try:
            return json.loads(response_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid server response: {response_line}") from exc


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
    host: Optional[str] = typer.Option(None, "--host", help="Server host"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port"),
):
    size = file_path.stat().st_size
    checksum = file_sha256(file_path)
    payload = file_path.read_bytes()

    response = send_command(
        f"SEND {file_path.name} {size} {checksum}",
        payload=payload,
        host=host,
        port=port,
    )
    require_ok(response)
    console.print(f"[green]Uploaded:[/green] {file_path.name}")


@app.command(name="list")
def list_files(
    host: Optional[str] = typer.Option(None, "--host", help="Server host"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port"),
):
    response = send_command("LIST", host=host, port=port)
    require_ok(response)
    files = response.get("files", [])

    table = Table(title="Personal Cloud Files")
    table.add_column("Name", style="cyan")
    table.add_column("Size (bytes)", justify="right")
    table.add_column("SHA256", style="magenta")
    table.add_column("Created At", style="green")

    for item in files:
        table.add_row(
            str(item.get("name", "")),
            str(item.get("size_bytes", "")),
            str(item.get("sha256", "")),
            str(item.get("created_at", "")),
        )

    console.print(table)


@app.command()
def delete(
    filename: str = typer.Argument(..., help="Remote filename to delete"),
    host: Optional[str] = typer.Option(None, "--host", help="Server host"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port"),
):
    response = send_command(f"DELETE {filename}", host=host, port=port)
    require_ok(response)
    console.print(f"[yellow]{response.get('message', 'Deleted')}[/yellow]")


if __name__ == "__main__":
    app()
