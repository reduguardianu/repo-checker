"""Cache of current git branch names, refreshed safely off the UI thread."""

from __future__ import annotations

import time

from . import git_backend as git
from .models import RepoConfig, expand_path


class BranchCache:
    """Reads branches in the background so refresh() never blocks the GUI.

    The window asks for `get(repo)`; if the value is stale, a background
    thread refreshes it and calls `callback` with the new value.
    """

    TTL = 120.0  # seconds

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._stamps: dict[str, float] = {}
        self._inflight: set[str] = set()
        self.callback = None  # optional fn() fired on the UI side after updates

    def get(self, repo: RepoConfig) -> str:
        name = repo.display_name
        if repo.branch:
            return repo.branch
        cached = self._values.get(name)
        if cached is not None and time.time() - self._stamps.get(name, 0) < self.TTL:
            return cached
        if name not in self._inflight:
            self._inflight.add(name)
            from threading import Thread

            Thread(target=self._refresh, args=(repo,), daemon=True).start()
        return cached or "-"

    def _refresh(self, repo: RepoConfig) -> None:
        name = repo.display_name
        try:
            branch = git.current_branch(expand_path(repo.path)) or "(detached)"
        except Exception:  # noqa: BLE001 - not a repo, git missing, ...
            branch = "-"
        self._values[name] = branch
        self._stamps[name] = time.time()
        self._inflight.discard(name)
        if self.callback is not None:
            try:
                self.callback()
            except Exception:  # noqa: BLE001
                pass
