"""Scheduler and worker threads: periodically checks repos, auto pulls.

Git work runs on a QThreadPool so the UI thread never blocks; results are
marshalled back through a queued signal.  Status transitions drive
notifications so a repo that stays broken for an hour only notifies once.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from . import config as config_mod
from . import git_backend as git
from . import notifier
from .models import (
    STATUS_BEHIND,
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNKNOWN,
    RepoConfig,
    RepoState,
    expand_path,
    worse_status,
)

log = logging.getLogger(__name__)

TICK_MS = 5000           # dispatch loop granularity
MAX_WORKERS = 3          # concurrent git operations
LOG_LIMIT = 300          # log lines kept per repo
MAX_BACKOFF = 8          # fetch failures multiply interval by 2**fails up to this


class _Task(QRunnable):
    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:  # pragma: no cover - executed on worker thread
        try:
            self._fn()
        except Exception:  # noqa: BLE001 - worker must never crash the pool
            log.exception("worker task crashed")


class Monitor(QObject):
    updated = pyqtSignal(str)           # a repo's state changed (repo name)
    refresh = pyqtSignal()              # global change (pause, add, remove...)
    log_changed = pyqtSignal(str)       # a repo produced log lines
    _result_ready = pyqtSignal(str, object)

    def __init__(self, app_config: config_mod.AppConfig) -> None:
        super().__init__()
        self._app_cfg = app_config
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(MAX_WORKERS)
        self._states: dict[str, RepoState] = {}
        self._next_check: dict[str, float] = {}
        self._busy: set[str] = set()
        self._failures: dict[str, int] = {}       # consecutive error runs
        self._logs: dict[str, deque[str]] = {}
        self._paused = False
        self._result_ready.connect(self._apply_result)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._dispatch_due)
        self._timer.start(TICK_MS)

        now = time.time()
        for i, repo in enumerate(app_config.repos):
            name = repo.display_name
            self._states[name] = RepoState()
            self._logs[name] = deque(maxlen=LOG_LIMIT)
            self._next_check[name] = now + i * 2.0   # stagger startup load

    # ------------------------------------------------------------------
    # public API (main thread)

    def state(self, name: str) -> RepoState:
        return self._states.get(name, RepoState())

    def repos(self) -> list[RepoConfig]:
        return list(self._app_cfg.repos)

    def log_lines(self, name: str) -> list[str]:
        return list(self._logs.get(name, ()))

    @property
    def paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        if self._paused != paused:
            self._paused = paused
            if not paused:
                self._dispatch_due()
            self.refresh.emit()

    def summary(self) -> str:
        """Tray tooltip style aggregate, e.g. '3 repos - 2 behind, 1 error'."""
        errors = behind = blocked = 0
        for repo in self._app_cfg.repos:
            st = self._states.get(repo.display_name, RepoState())
            if st.status in (STATUS_ERROR,):
                errors += 1
            elif st.status == STATUS_BLOCKED:
                blocked += 1
            elif st.status == STATUS_BEHIND or st.behind:
                behind += 1
        parts = []
        if behind:
            parts.append(f"{behind} behind")
        if blocked:
            parts.append(f"{blocked} blocked")
        if errors:
            parts.append(f"{errors} error" + ("s" if errors > 1 else ""))
        summary = "; ".join(parts) if parts else "all up to date"
        if self._paused:
            summary += " (paused)"
        return summary

    def overall_status(self) -> str:
        """Worst status across all repos, for tray icon coloring."""
        if self._paused:
            return "paused"
        worst = STATUS_OK
        for repo in self._app_cfg.repos:
            worst = worse_status(
                worst, self._states.get(repo.display_name, RepoState()).status
            )
        return worst

    def check_now(self, name: str) -> None:
        self._start_check(name)

    def check_all(self) -> None:
        for repo in self._app_cfg.repos:
            self._start_check(repo.display_name)

    def add_repo(self, repo: RepoConfig) -> None:
        config_mod.validate_new_repo(self._app_cfg, repo)
        self._app_cfg.repos.append(repo)
        config_mod.save(self._app_cfg)
        name = repo.display_name
        self._states.update({name: RepoState()})
        self._logs[name] = deque(maxlen=LOG_LIMIT)
        self._next_check[name] = time.time()
        self.refresh.emit()
        self._dispatch_due()

    def remove_repo(self, name: str) -> None:
        for repo in list(self._app_cfg.repos):
            if repo.display_name == name:
                self._app_cfg.repos.remove(repo)
                break
        self._states.pop(name, None)
        self._logs.pop(name, None)
        self._next_check.pop(name, None)
        self._busy.discard(name)
        self._failures.pop(name, None)
        config_mod.save(self._app_cfg)
        self.refresh.emit()

    def shutdown(self) -> None:
        self._timer.stop()
        self._pool.clear()

    def _effective_interval(self, repo: RepoConfig) -> int:
        return repo.interval_minutes or self._app_cfg.interval_minutes

    # ------------------------------------------------------------------
    # scheduling (main thread)

    def _dispatch_due(self) -> None:
        if self._paused:
            return
        now = time.time()
        for repo in self._app_cfg.repos:
            name = repo.display_name
            if name in self._busy:
                continue
            if self._next_check.get(name, now) <= now:
                self._start_check(name)

    def _start_check(self, name: str) -> None:
        if self._paused:
            return
        for repo in self._app_cfg.repos:
            if repo.display_name == name:
                if name in self._busy:
                    return
                self._busy.add(name)
                self._pool.start(_Task(lambda cfg=repo: self._execute(cfg)))
                return

    # ------------------------------------------------------------------
    # execution (worker thread)

    def _execute(self, repo: RepoConfig) -> None:
        """Run a full check cycle on a worker thread; emit results."""
        try:
            state, lines = self._check(repo)
        except git.GitError as exc:
            state = RepoState(status=STATUS_ERROR, message=exc.detail or str(exc))
            lines = [f"error: {exc.detail or exc}"]
            if exc.output:
                state.message = f"{exc.detail}\n{exc.output}".strip()
                lines.append(exc.output.strip())
        except Exception as exc:  # noqa: BLE001
            msg = f"unexpected error: {exc!r}"
            state = RepoState(status=STATUS_ERROR, message=msg)
            lines = [msg]

        lines.append(_stamp(f"status: {state.status}, behind {state.behind}, "
                            f"ahead {state.ahead}, dirty={state.dirty}"))
        try:
            self._result_ready.emit(repo.display_name, (repo, state, lines))
        except RuntimeError:  # app is shutting down
            pass

    def _check(self, repo: RepoConfig) -> tuple[RepoState, list[str]]:
        lines: list[str] = []
        state = RepoState(status=STATUS_UNKNOWN)
        path = expand_path(repo.path)
        stamp = _stamp

        if not os.path.isdir(path):
            raise git.GitError(f"directory does not exist: {path}")
        if not git.is_work_tree(path):
            raise git.GitError(f"not a git repository: {path}")

        branch = repo.branch or git.current_branch(path)
        if not branch:
            raise git.GitError("HEAD is detached; cannot determine branch")
        up_ref = git.upstream(path, branch)
        lines.append(stamp(f"branch {branch} vs upstream {up_ref}"))

        state.dirty = git.is_dirty(path)
        git.fetch(path)
        lines.append(stamp("fetch ok"))
        state.last_check = time.time()

        ahead, behind = git.ahead_behind(path, branch, up_ref)
        state.ahead, state.behind = ahead, behind

        if behind == 0:
            state.status = STATUS_OK
            state.message = (
                f"up to date (local commits ahead: {ahead})" if ahead else "up to date"
            )
            return state, lines

        if not repo.auto_pull:
            state.status = STATUS_BEHIND
            state.message = (
                f"{behind} upstream commit(s) available "
                "(auto pull disabled for this repo)"
            )
            return state, lines

        # Auto pull is enabled: try to fast-forward safely.
        if state.dirty:
            state.status = STATUS_BLOCKED
            state.message = (
                f"{behind} upstream commit(s), but the working tree has "
                "local changes; pull skipped"
            )
            return state, lines

        if not git.is_ancestor(path, branch, up_ref):
            state.status = STATUS_BLOCKED
            state.message = (
                f"{behind} upstream commit(s), branch diverged from upstream "
                f"(ahead by {ahead}); rebase or merge needed"
            )
            return state, lines

        git.pull_ff(path)
        # Re-verify; a racing push could leave something new (rare).
        ahead2, behind2 = git.ahead_behind(path, branch, up_ref)
        state.ahead, state.behind = ahead2, behind2
        state.status = STATUS_OK if behind2 == 0 else STATUS_BEHIND
        state.pulled = behind - behind2
        state.message = f"fast-forwarded {behind - behind2} commit(s) from {up_ref}"
        lines.append(stamp(state.message))
        return state, lines

    # ------------------------------------------------------------------
    # results (main thread)

    def _apply_result(self, name: str, payload: object) -> None:
        repo, state, lines = payload  # type: ignore[misc]
        previous = self._states.get(name, RepoState())
        self._states[name] = state
        log_buffer = self._logs.setdefault(name, deque(maxlen=LOG_LIMIT))
        log_buffer.extend(lines)
        self._busy.discard(name)
        self.log_changed.emit(name)

        # Notification policy: on transitions, never per-check spam.
        pulled = state.pulled > 0
        if state.status == STATUS_ERROR:
            self._failures[name] = self._failures.get(name, 0) + 1
            if self._app_cfg.notify_on_failure and previous.status != STATUS_ERROR:
                notifier.notify(f"Repo Checker - {name}", state.message, "critical")
        else:
            self._failures[name] = 0
            if state.status == STATUS_BLOCKED and previous.status != STATUS_BLOCKED:
                if self._app_cfg.notify_on_failure:
                    notifier.notify(f"Repo Checker - {name}", state.message)
            elif state.status == STATUS_BEHIND and previous.status != STATUS_BEHIND:
                if self._app_cfg.notify_on_update_available:
                    notifier.notify(f"Repo Checker - {name}", state.message)
            if pulled and self._app_cfg.notify_on_success:
                notifier.notify(f"Repo Checker - {name}", state.message)

        # Schedule the next check (with backoff after consecutive errors).
        interval = self._effective_interval(repo) * 60
        if state.status == STATUS_ERROR:
            interval *= min(MAX_BACKOFF, 2 ** self._failures.get(name, 1))
        self._next_check[name] = time.time() + max(interval, TICK_MS / 1000 * 2)
        self.updated.emit(name)


def _stamp(text: str) -> str:
    return time.strftime("%H:%M:%S ") + text
