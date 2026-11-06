"""Desktop notifications via org.freedesktop.Notifications (notify-send)."""

from __future__ import annotations

import logging
import subprocess
import shutil

log = logging.getLogger(__name__)

APP_ID = "repo-checker"


def available() -> bool:
    return shutil.which("notify-send") is not None


def notify(summary: str, body: str = "", urgency: str = "normal") -> None:
    """Send a desktop notification.  Best effort: logs when unavailable."""
    cmd = ["notify-send", "-a", APP_ID, "-u", urgency, summary]
    if body:
        cmd.append(body)
    try:
        subprocess.run(
            cmd,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        log.warning("notify-send not installed; notification dropped: %s", summary)
    except subprocess.TimeoutExpired:
        log.warning("notify-send timed out; notification dropped: %s", summary)
