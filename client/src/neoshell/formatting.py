"""Formatting utilities for display, duration parsing, and tables."""

from __future__ import annotations

import re
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def parse_duration_to_seconds(value: str) -> int:
    """Parse a duration string (e.g. 60s, 30m, 1h, 24h, 7d) into seconds.
    
    If given a plain integer string, returns it as seconds.
    Raises ValueError on invalid formats.
    """
    raw = value.strip().lower()
    if not raw:
        raise ValueError("Empty duration string")

    match = re.fullmatch(r"(\d+)\s*([smhd]?)", raw)
    if not match:
        raise ValueError(
            f"Invalid duration format: '{value}'. Use formats like 60s, 30m, 1h, 24h, 7d."
        )

    count_str, unit = match.groups()
    count = int(count_str)

    multiplier = {
        "": 1,
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }[unit]

    return count * multiplier


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 0:
        return f"{size_bytes} B"
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PiB"


def create_file_table(files: list[dict], title: str = "Neoshell Files") -> Table:
    """Build a Rich Table for listing files."""
    table = Table(title=title, show_lines=False)
    table.add_column("Name", style="bold cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("SHA256", style="dim magenta")
    table.add_column("Uploaded At", style="yellow")

    for f in files:
        name = str(f.get("name", ""))
        size_val = f.get("size_bytes", 0)
        try:
            size_str = format_size(int(size_val))
        except (ValueError, TypeError):
            size_str = str(size_val)
        sha = str(f.get("sha256", ""))
        # Truncate SHA for clean display if long
        sha_display = f"{sha[:12]}...{sha[-8:]}" if len(sha) >= 32 else sha
        created_at = str(f.get("created_at", ""))
        table.add_row(name, size_str, sha_display, created_at)

    return table


def create_transfer_progress() -> Progress:
    """Create a standard Rich Progress instance for streaming transfers."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )
