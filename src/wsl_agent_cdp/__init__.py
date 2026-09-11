"""Console entry point for the WSL CDP bridge."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    """Hand control to the bridge script while preserving signals and exit code."""
    script = Path(__file__).resolve().parents[2] / "cdp-bridge"
    if not script.is_file():
        raise SystemExit(
            "cdp-bridge could not find its project script. "
            "Run it from a source checkout with: ./cdp-bridge help"
        )
    os.execv("/usr/bin/env", ("env", "bash", str(script), *sys.argv[1:]))
