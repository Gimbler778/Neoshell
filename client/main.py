#!/usr/bin/env python3
"""Compatibility shim for running the CLI directly during development."""

import sys
from pathlib import Path

# Ensure client/src is on sys.path for direct execution
src_dir = Path(__file__).resolve().parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from neoshell.cli import main

if __name__ == "__main__":
    main()
