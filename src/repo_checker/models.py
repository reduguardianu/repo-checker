"""Data model for repo configuration and monitoring state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

# Possible status values for a monitored repository.
STATUS_UNKNOWN = "unknown"      # never checked yet
STATUS_OK = "ok"                # in sync (possibly with local commits ahead)
STATUS_BEHIND = "behind"        # upstream has commits, auto pull disabled
STATUS_BLOCKED = "blocked"      # upstream has commits, auto pull attempted but prevented
STATUS_ERROR = "error"          # fetch/auth/not a repo/no upstream/... failure

STATUS_TEXT = {
    STATUS_UNKNOWN: "Pending",
    STATUS_OK: "Up to date",
    STATUS_BEHIND: "Updates available",
    STATUS_BLOCKED: "Pull blocked",
    STATUS_ERROR: "Error",
}

STATUS_HEX = {
    STATUS_UNKNOWN: "#94a3b8",
    STATUS_OK: "#22c55e",
    STATUS_BEHIND: "#f59e0b",
    STATUS_BLOCKED: "#f59e0b",
    STATUS_ERROR: "#ef4444",
}

# Severity ranking used to color the tray icon (higher wins).
_STATUS_RANK = {
    STATUS_UNKNOWN: 0,
    STATUS_OK: 1,
    STATUS_BEHIND: 2,
    STATUS_BLOCKED: 2,
    STATUS_ERROR: 3,
}


def worse_status(a: str, b: str) -> str:
    """Return the more severe of two statuses."""
    return a if _STATUS_RANK.get(a, 0) >= _STATUS_RANK.get(b, 0) else b


def relative_time(ts: float) -> str:
    """Human readable 'x min ago' style timestamp. 0 means 'never'."""
    if not ts:
        return "never"
    delta = int(time.time() - ts)
    if delta < 0:
        delta = 0
    if delta < 15:
        return "just now"
    if delta < 90:
        return f"{max(1, delta // 30 * 30)} sec ago"
    minutes = delta // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} h ago"
    return f"{hours // 24} d ago"


def expand_path(path: str) -> str:
    """Expand ~ and environment variables in a repo path."""
    return str(Path(path).expanduser())


def display_name_for(path: str, name: str = "") -> str:
    """Repo display name: configured name or the directory's basename."""
    if name:
        return name
    expanded = expand_path(path)
    if expanded.endswith("/"):
        expanded = expanded.rstrip("/") or expanded
    return Path(expanded).name or expanded


@dataclass
class RepoConfig:
    """One monitored repository, as stored in config.toml."""

    path: str
    name: str = ""                   # optional display name override
    branch: str = ""                 # optional; defaults to the checked out branch
    auto_pull: bool = True           # per-repo override
    interval_minutes: int = 0        # per-repo override; 0 = use global interval

    @property
    def display_name(self) -> str:
        return display_name_for(self.path, self.name)


@dataclass
class RepoState:
    """Last observed state of a monitored repository."""

    status: str = STATUS_UNKNOWN
    behind: int = 0                  # commits on upstream missing locally
    ahead: int = 0                   # local commits not pushed
    dirty: bool = False              # uncommitted local changes
    last_check: float = 0.0
    last_pull: float = 0.0
    pulled: int = 0                  # commit count of the last successful pull
    message: str = ""                # success summary, blocked reason or error text

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK
