"""Install a desktop launcher entry + hicolor icon for repo_checker.

Usage: .venv/bin/python scripts/install_desktop.py [--uninstall]

Writes:
  $XDG_DATA_HOME/applications/repo-checker.desktop
  $XDG_DATA_HOME/icons/hicolor/256x256/apps/repo-checker.png

The Exec line prefers the installed `repo-checker` console script and
falls back to `python -m repo_checker` using the interpreter that runs
this script (so a venv install works too).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from repo_checker.icons import render


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))


def exec_line() -> str:
    """Sanely quoted desktop-Exec command to start the app."""
    binary = shutil.which("repo-checker")
    if binary:
        return f'"{binary}"'
    return f'"{sys.executable}" -m repo_checker'


def install() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication  # noqa: F401 - needed for QPixmap render

    app = QApplication.instance() or QApplication([])  # noqa: F841 - must exist for QPixmap
    _ = app

    # 1. Icon (status "ok" green dot serves as the static launcher icon).
    icon_dir = data_home() / "icons/hicolor/256x256/apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    icon_path = icon_dir / "repo-checker.png"
    ok = render("ok", 256).save(str(icon_path), "PNG")
    if not ok:
        print(f"failed to write icon {icon_path}", file=sys.stderr)
        return 1
    print(f"icon:      {icon_path}")

    # 2. Desktop entry.
    apps_dir = data_home() / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    entry = apps_dir / "repo-checker.desktop"
    content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",  # Desktop Entry Spec version, not the app version
        "Name=Repo Checker",
        "GenericName=Git repository monitor",
        "Comment=Monitor git repos, auto fast-forward pull, tray status",
        f"Exec={exec_line()}",
        "Icon=repo-checker",
        "Terminal=false",
        "Categories=Utility;",
        "Keywords=git;repo;monitor;pull;checker;",
        "StartupNotify=false",
        "X-GNOME-UsesNotifications=true",
        "",
    ])
    entry.write_text(content, encoding="utf-8")
    entry.chmod(0o644)
    print(f"entry:     {entry}")

    # 3. Refresh caches when available.
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(apps_dir)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        print("caches:    updated desktop database")
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(
            ["gtk-update-icon-cache", "-qtf", str(data_home() / "icons/hicolor")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    return 0


def uninstall() -> int:
    removed = 0
    for path in [
        data_home() / "applications/repo-checker.desktop",
        data_home() / "icons/hicolor/256x256/apps/repo-checker.png",
    ]:
        try:
            path.unlink()
            removed += 1
            print(f"removed:   {path}")
        except FileNotFoundError:
            print(f"missing:   {path}")
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(data_home() / "applications")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    return 0 if removed else 1


if __name__ == "__main__":
    sys.exit(uninstall() if "--uninstall" in sys.argv[1:] else install())
