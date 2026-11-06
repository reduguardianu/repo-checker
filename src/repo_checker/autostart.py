"""XDG autostart entry management (launch at login)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_DESKTOP_NAME = "repo-checker.desktop"
_AUTOSTART_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "autostart"
_DESKTOP_FILE = _AUTOSTART_DIR / _DESKTOP_NAME


def _exec_line() -> str:
    binary = shutil.which("repo-checker")
    if binary:
        return binary
    python = shutil.which("python3") or "python3"
    return f"{python} -m repo_checker"


def enabled() -> bool:
    return _DESKTOP_FILE.is_file()


def enable() -> None:
    _AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Exec={_exec_line()}\n"
        "Name=Repo Checker\n"
        "Icon=repo-checker\n"
        "Comment=Monitor git repositories and auto pull\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    _DESKTOP_FILE.write_text(content, encoding="utf-8")


def disable() -> None:
    try:
        _DESKTOP_FILE.unlink()
    except FileNotFoundError:
        pass
