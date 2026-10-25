"""Command Line Interface for Neoshell."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import typer
from rich.panel import Panel

from neoshell import __version__
from neoshell.api import (
    ApiClient,
    AuthenticationError,
    ChecksumMismatchError,
    ConnectionFailedError,
    NeoshellError,
    NotFoundError,
    ServerError,
    TimeoutError,
)
from neoshell.config import (
    DEFAULT_SERVER_URL,
    clear_config,
    clear_saved_token,
    get_config_file_path,
    load_saved_config,
    resolve_config,
    save_config,
)
from neoshell.formatting import (
    console,
    create_file_table,
    create_transfer_progress,
    err_console,
    format_size,
    parse_duration_to_seconds,
)

app = typer.Typer(
    name="neoshell",
    help="Neoshell - Personal Cloud File Manager CLI",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass
class State:
    url: Optional[str] = None
    token: Optional[str] = None
    json_mode: bool = False
    quiet: bool = False
    timeout: float = 30.0


state = State()


def reset_state() -> None:
    """Reset CLI state to defaults."""
    state.url = None
    state.token = None
    state.json_mode = False
    state.quiet = False
    state.timeout = 30.0


def get_api_client(
    override_url: Optional[str] = None,
    override_token: Optional[str] = None,
) -> ApiClient:
    """Build ApiClient using resolved configuration and CLI state."""
    cfg = resolve_config(cli_url=override_url or state.url, cli_token=override_token or state.token)
    return ApiClient(base_url=cfg.url, token=cfg.token, timeout=state.timeout)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard using native OS tools."""
    try:
        if os.name == "nt":
            subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
            return True
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return True
        for cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
            if shutil.which(cmd[0]):
                subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                return True
    except Exception:
        pass
    return False


def handle_error(exc: Exception, json_mode: bool = False) -> None:
    """Render error appropriately based on format mode and exit with code 1."""
    if json_mode or state.json_mode:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
    else:
        err_console.print(f"[bold red]Error:[/bold red] {exc}")
    raise typer.Exit(code=1)


def version_callback(value: bool) -> None:
    """Callback for --version option."""
    if value:
        console.print(f"neoshell-cli v{__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
    url: Optional[str] = typer.Option(
        None, "--url", help="Override Neoshell server base URL", envvar="NEOSHELL_URL"
    ),
    token: Optional[str] = typer.Option(
        None, "--token", help="Override auth token", envvar="NEOSHELL_TOKEN"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON where applicable"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress non-essential progress and styling"
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", help="HTTP timeout in seconds"
    ),
) -> None:
    """Neoshell Personal Cloud File Manager CLI."""
    state.url = url
    state.token = token
    state.json_mode = json_output
    state.quiet = quiet
    state.timeout = timeout


@app.command()
def login(
    url: Optional[str] = typer.Option(None, "--url", help="Server URL (e.g. https://YOUR-APP.example.com)"),
    token: Optional[str] = typer.Option(None, "--token", help="Shared authentication token"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
) -> None:
    """Configure and verify connection settings."""
    is_json = json_output or state.json_mode
    current = load_saved_config()
    target_url = url or state.url or current.get("url") or DEFAULT_SERVER_URL
    target_token = token if token is not None else (state.token if state.token is not None else current.get("token"))

    # If URL is being configured, verify it first via /health
    test_client = ApiClient(base_url=target_url, token=target_token, timeout=state.timeout)
    if not state.quiet and not is_json:
        console.print(f"Connecting to [bold cyan]{target_url}[/bold cyan]...")

    try:
        health_resp = test_client.health()
        if not health_resp.get("ok"):
            raise ServerError(f"Health check failed: {health_resp}")
    except Exception as exc:
        handle_error(exc, json_mode=is_json)

    try:
        saved_path = save_config(url=target_url, token=target_token)
    except Exception as exc:
        handle_error(exc, json_mode=is_json)

    if is_json:
        print(json.dumps({"ok": True, "url": target_url, "token_configured": bool(target_token), "config_path": str(saved_path)}))
    else:
        console.print(f"[bold green]Successfully configured Neoshell![/bold green]")
        console.print(f"Server URL: [cyan]{target_url}[/cyan]")
        console.print(f"Token:      [yellow]{'Configured' if target_token else 'None'}[/yellow]")
        console.print(f"Saved to:   [dim]{saved_path}[/dim]")


@app.command()
def logout(
    all_config: bool = typer.Option(False, "--all", help="Delete entire configuration file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Clear saved authentication token or entire configuration."""
    is_json = json_output or state.json_mode
    if all_config:
        cleared = clear_config()
        msg = "Configuration removed." if cleared else "No configuration found to remove."
    else:
        cleared = clear_saved_token()
        msg = "Token cleared." if cleared else "No saved token found to clear."

    if is_json:
        print(json.dumps({"ok": True, "message": msg}))
    else:
        console.print(f"[yellow]{msg}[/yellow]")


@app.command()
def status(
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show connection status, stored token presence, and server health."""
    is_json = json_output or state.json_mode
    cfg = resolve_config(cli_url=url or state.url, cli_token=token or state.token)
    client = ApiClient(base_url=cfg.url, token=cfg.token, timeout=state.timeout)

    is_healthy = False
    file_count: Optional[int] = None
    health_error: Optional[str] = None

    try:
        h = client.health()
        is_healthy = bool(h.get("ok"))
    except Exception as exc:
        health_error = str(exc)

    if is_healthy:
        try:
            files = client.list_files()
            file_count = len(files)
        except Exception:
            file_count = None

    if is_json:
        print(json.dumps({
            "ok": is_healthy,
            "url": cfg.url,
            "token_configured": bool(cfg.token),
            "healthy": is_healthy,
            "file_count": file_count,
            "error": health_error,
            "config_file": str(get_config_file_path()),
        }, indent=2))
        return

    status_str = "[bold green]Online[/bold green]" if is_healthy else f"[bold red]Offline ({health_error})[/bold red]"
    token_str = "[green]Configured[/green]" if cfg.token else "[dim]Not configured[/dim]"
    count_str = str(file_count) if file_count is not None else "[dim]N/A[/dim]"

    content = (
        f"[bold]Server URL:[/bold]        {cfg.url}\n"
        f"[bold]Health Status:[/bold]     {status_str}\n"
        f"[bold]Auth Token:[/bold]        {token_str}\n"
        f"[bold]Files on Server:[/bold]   {count_str}\n"
        f"[bold]Config Path:[/bold]       {get_config_file_path()}"
    )
    console.print(Panel(content, title="Neoshell Status", expand=False))


@app.command()
def upload(
    paths: List[Path] = typer.Argument(..., help="One or more local file paths to upload"),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Upload one or more files to Neoshell."""
    is_json = json_output or state.json_mode
    client = get_api_client(override_url=url, override_token=token)
    failed = False
    uploaded_files = []

    for file_path in paths:
        if not file_path.exists():
            err_console.print(f"[bold red]File not found:[/bold red] {file_path}")
            failed = True
            continue
        if file_path.is_dir():
            err_console.print(f"[bold red]Cannot upload a directory:[/bold red] {file_path}")
            failed = True
            continue

        try:
            if state.quiet or is_json:
                resp = client.upload_file(file_path)
            else:
                with create_transfer_progress() as progress:
                    task = progress.add_task(
                        "upload",
                        filename=file_path.name,
                        total=file_path.stat().st_size,
                    )
                    resp = client.upload_file(
                        file_path,
                        progress_callback=lambda n: progress.update(task, advance=n),
                    )

            uploaded_files.append(resp.get("file", {"name": file_path.name}))
            if not state.quiet and not is_json:
                console.print(f"[bold green]Uploaded:[/bold green] {file_path.name}")
        except Exception as exc:
            err_console.print(f"[bold red]Failed uploading {file_path.name}:[/bold red] {exc}")
            failed = True

    if is_json:
        print(json.dumps({"ok": not failed, "uploaded": uploaded_files}))

    if failed:
        raise typer.Exit(code=1)


@app.command(name="list")
def list_files(
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List all stored files in Neoshell."""
    is_json = json_output or state.json_mode
    client = get_api_client(override_url=url, override_token=token)
    try:
        files = client.list_files()
    except Exception as exc:
        handle_error(exc, json_mode=is_json)

    if is_json:
        print(json.dumps(files, indent=2))
    else:
        if not files:
            console.print("[dim]No files found in storage.[/dim]")
        else:
            console.print(create_file_table(files))


@app.command()
def download(
    name: str = typer.Argument(..., help="Name of file in Neoshell storage"),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Destination file or directory path"
    ),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Download a file and verify its SHA-256 checksum."""
    is_json = json_output or state.json_mode
    client = get_api_client(override_url=url, override_token=token)

    dest_path: Path
    if output:
        if output.is_dir():
            dest_path = output / name
        else:
            dest_path = output
    else:
        dest_path = Path.cwd() / name

    try:
        if state.quiet or is_json:
            saved_path = client.download_file(name, dest_path)
        else:
            # Look up file info for total size if possible
            total_size = None
            try:
                info = client.get_file_info(name)
                total_size = int(info.get("size_bytes", 0))
            except Exception:
                pass

            with create_transfer_progress() as progress:
                task = progress.add_task("download", filename=name, total=total_size)
                saved_path = client.download_file(
                    name,
                    dest_path,
                    progress_callback=lambda n: progress.update(task, advance=n),
                )

        if is_json:
            print(json.dumps({"ok": True, "name": name, "path": str(saved_path)}))
        else:
            console.print(f"[bold green]Downloaded:[/bold green] {name} -> [cyan]{saved_path}[/cyan]")
    except Exception as exc:
        handle_error(exc, json_mode=is_json)


@app.command()
def share(
    name: str = typer.Argument(..., help="Remote filename to share"),
    expires: str = typer.Option(
        "24h", "--expires", help="Expiration duration (e.g. 60s, 30m, 1h, 24h, 7d)"
    ),
    clip: bool = typer.Option(
        False, "--clip", help="Copy the generated share URL to the system clipboard"
    ),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Generate a temporary presigned download link for a file."""
    is_json = json_output or state.json_mode
    try:
        expires_in = parse_duration_to_seconds(expires)
    except ValueError as exc:
        handle_error(exc, json_mode=is_json)

    client = get_api_client(override_url=url, override_token=token)
    try:
        resp = client.share_file(name, expires_in=expires_in)
    except Exception as exc:
        handle_error(exc, json_mode=is_json)

    share_url = resp.get("url", "")
    expires_at = resp.get("expires_at", "")

    copied = False
    if clip and share_url:
        copied = copy_to_clipboard(share_url)

    if is_json:
        print(json.dumps({
            "ok": True,
            "name": name,
            "url": share_url,
            "expires_at": expires_at,
            "copied_to_clipboard": copied,
        }, indent=2))
        return

    console.print(f"[bold green]Share link generated for '{name}':[/bold green]")
    console.print(f"[cyan]{share_url}[/cyan]")
    console.print(f"[dim]Expires at: {expires_at}[/dim]")
    if clip:
        if copied:
            console.print("[green]Copied share link to clipboard![/green]")
        else:
            console.print("[yellow]Clipboard utility not found or copy failed.[/yellow]")


@app.command()
def delete(
    names: List[str] = typer.Argument(..., help="One or more remote filenames to delete"),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip confirmation prompt"
    ),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Delete one or more files from Neoshell."""
    is_json = json_output or state.json_mode
    if not yes and not state.quiet and not is_json:
        confirm_msg = f"Are you sure you want to delete {len(names)} file(s)?"
        if not typer.confirm(confirm_msg, default=False):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=0)

    client = get_api_client(override_url=url, override_token=token)
    failed = False
    deleted_names = []

    for name in names:
        try:
            resp = client.delete_file(name)
            deleted_names.append(name)
            if not state.quiet and not is_json:
                console.print(f"[yellow]{resp.get('message', f'Deleted {name}')}[/yellow]")
        except Exception as exc:
            err_console.print(f"[bold red]Failed deleting {name}:[/bold red] {exc}")
            failed = True

    if is_json:
        print(json.dumps({"ok": not failed, "deleted": deleted_names}))

    if failed:
        raise typer.Exit(code=1)


@app.command()
def info(
    name: str = typer.Argument(..., help="Remote filename to inspect"),
    url: Optional[str] = typer.Option(None, "--url", help="Server URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Auth token"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """View metadata and checksum of a remote file without downloading."""
    is_json = json_output or state.json_mode
    client = get_api_client(override_url=url, override_token=token)
    try:
        file_info = client.get_file_info(name)
    except Exception as exc:
        handle_error(exc, json_mode=is_json)

    if is_json:
        print(json.dumps(file_info, indent=2))
        return

    size_val = file_info.get("size_bytes", 0)
    try:
        size_str = f"{format_size(int(size_val))} ({size_val} bytes)"
    except Exception:
        size_str = str(size_val)

    details = (
        f"[bold]Name:[/bold]        {file_info.get('name')}\n"
        f"[bold]Size:[/bold]        {size_str}\n"
        f"[bold]SHA256:[/bold]      [magenta]{file_info.get('sha256')}[/magenta]\n"
        f"[bold]Uploaded At:[/bold] {file_info.get('created_at')}"
    )
    console.print(Panel(details, title=f"File: {name}", expand=False))


def main() -> None:
    """Entry point for the neoshell command."""
    try:
        app()
    except Exception as exc:
        handle_error(exc)


if __name__ == "__main__":
    main()
