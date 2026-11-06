"""Configuration load/save for repo_checker (TOML in ~/.config/repo_checker)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

from . import autostart
from .models import RepoConfig

APP_NAME = "repo-checker"
CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / APP_NAME

DEFAULT_INTERVAL_MINUTES = 15


@dataclass
class AppConfig:
    """Everything persisted in config.toml."""

    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    auto_pull: bool = True
    notify_on_failure: bool = True
    notify_on_success: bool = True
    notify_on_update_available: bool = False
    start_minimized: bool = True
    repos: list[RepoConfig] = field(default_factory=list)

    @property
    def names(self) -> set[str]:
        return {r.display_name for r in self.repos}

    @property
    def paths(self) -> set[str]:
        return {r.path for r in self.repos}


def _parse_repo(raw: dict[str, Any]) -> RepoConfig:
    return RepoConfig(
        path=str(raw.get("path", "")),
        name=str(raw.get("name", "")),
        branch=str(raw.get("branch", "")),
        auto_pull=bool(raw.get("auto_pull", True)),
        interval_minutes=int(raw.get("interval_minutes", 0) or 0),
    )


def load(path: Path = CONFIG_FILE) -> AppConfig:
    """Load config from disk, creating a default file on first run."""
    cfg = AppConfig()
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise RuntimeError(f"Invalid config file {path}: {exc}") from exc
        general = data.get("general", {}) or {}
        cfg.interval_minutes = max(1, int(general.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)))
        cfg.auto_pull = bool(general.get("auto_pull", True))
        cfg.notify_on_failure = bool(general.get("notify_on_failure", True))
        cfg.notify_on_success = bool(general.get("notify_on_success", True))
        cfg.notify_on_update_available = bool(general.get("notify_on_update_available", False))
        cfg.start_minimized = bool(general.get("start_minimized", True))
        repos_section = data.get("repos", []) or []
        cfg.repos = [_parse_repo(r) for r in repos_section if isinstance(r, dict)]
    else:
        save(cfg, path)
    return cfg


def save(cfg: AppConfig, path: Path = CONFIG_FILE) -> None:
    """Write config back to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "general": {
            "interval_minutes": cfg.interval_minutes,
            "auto_pull": cfg.auto_pull,
            "notify_on_failure": cfg.notify_on_failure,
            "notify_on_success": cfg.notify_on_success,
            "notify_on_update_available": cfg.notify_on_update_available,
            "start_minimized": cfg.start_minimized,
        },
        "repos": [
            {
                "path": r.path,
                "name": r.name,
                "branch": r.branch,
                "auto_pull": r.auto_pull,
                "interval_minutes": r.interval_minutes,
            }
            for r in cfg.repos
        ],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
    tmp.replace(path)


def validate_new_repo(cfg: AppConfig, repo: RepoConfig) -> None:
    """Raise ValueError if the repo would clash with an existing entry."""
    if not repo.path:
        raise ValueError("Repository path is required.")
    if repo.path not in cfg.paths and repo.display_name in cfg.names:
        raise ValueError(
            f"A repository named {repo.display_name!r} already exists. "
            "Choose a different name."
        )
    if repo.path in cfg.paths:
        raise ValueError("This repository path is already being monitored.")


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def default_config_with_example(cfg: AppConfig) -> None:
    """Nothing to do for now; hook for future default repo seeding."""
    _ = cfg  # silence linters; kept for API stability


__all__ = [
    "APP_NAME",
    "AppConfig",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "STATE_DIR",
    "autostart",
    "ensure_state_dir",
    "load",
    "save",
    "validate_new_repo",
]
