"""Helpers to locate bundled resource files (works in source and frozen builds)."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Returns a path to a bundled resource.

    In a PyInstaller build resources live under ``sys._MEIPASS``; when running
    from source they live next to the Python files.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)
