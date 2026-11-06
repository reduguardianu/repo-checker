"""Git operations performed via the system git binary (subprocess).

Using the user's own git install means credentials, ssh-agent and
host-specific config just work.  All commands are non-interactive
(strict timeouts, no terminal prompts) so a hung credential prompt can
never freeze the UI thread.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

GIT_TIMEOUT = 60.0


class GitError(Exception):
    """A git command failed.  `.output` holds stdout/stderr for display."""

    def __init__(self, detail: str, output: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.output = output


@dataclass
class CommandResult:
    args: tuple[str, ...]
    stdout: str
    stderr: str


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # Never prompt for credentials; let ssh/askpass helpers resolve
    # non-interactively or fail fast.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "/bin/true"
    env["SSH_ASKPASS_REQUIRE"] = "force"
    return env


def _run(path: str, *args: str, timeout: float = GIT_TIMEOUT) -> CommandResult:
    if not os.path.isdir(path):
        raise GitError(f"directory does not exist: {path}")
    try:
        proc = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_env(),
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git {' '.join(args)} timed out after {timeout:.0f}s", ""
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise GitError(f"`git {' '.join(args)}` failed", detail)
    return CommandResult(args, proc.stdout, proc.stderr)


def is_work_tree(path: str) -> bool:
    """True if path is inside a git working tree."""
    try:
        _run(path, "rev-parse", "--is-inside-work-tree")
        return True
    except GitError:
        return False


def fetch(path: str) -> None:
    """Fetch all remotes; raises GitError on network/auth failure."""
    _run(path, "fetch", "--all", "--quiet")


def is_dirty(path: str) -> bool:
    """True if the working tree has uncommitted changes (tracked+untracked)."""
    return bool(_run(path, "status", "--porcelain").stdout.strip())


def current_branch(path: str) -> str | None:
    """Checked out branch name; None when HEAD is detached."""
    out = _run(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return None if out == "HEAD" else out


def upstream(path: str, branch: str) -> str:
    """Upstream ref of a branch, e.g. 'origin/main'."""
    try:
        return _run(path, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}").stdout.strip()
    except GitError as exc:
        combined = f"{exc.detail} {exc.output}".lower()
        if "no upstream" in combined or "ambiguous argument" in combined:
            raise GitError(
                f"branch {branch!r} has no upstream configured",
                exc.output,
            ) from exc
        raise


def ahead_behind(path: str, branch: str, upstream_ref: str) -> tuple[int, int]:
    """(ahead, behind) counts of branch vs upstream_ref."""
    out = _run(
        path, "rev-list", "--left-right", "--count", f"{branch}...{upstream_ref}"
    ).stdout.split()
    ahead, behind = int(out[0]), int(out[1])
    return ahead, behind


def is_ancestor(path: str, ancestor: str, descendant: str) -> bool:
    """True if `ancestor` is an ancestor of `descendant` (fast-forward possible)."""
    if not os.path.isdir(path):
        raise GitError(f"directory does not exist: {path}")
    try:
        proc = subprocess.run(
            ["git", "-C", path, "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, env=_env(),
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git merge-base --is-ancestor timed out after {GIT_TIMEOUT:.0f}s", ""
        ) from exc
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False  # merge-base reports "is not an ancestor" with exit 1
    raise GitError(
        "`git merge-base --is-ancestor` failed",
        (proc.stderr or proc.stdout).strip(),
    )


def pull_ff(path: str) -> str:
    """Fast-forward only pull. Returns combined git output (informational)."""
    result = _run(path, "merge", "--ff-only", "--quiet", "@{upstream}")
    return result.stderr or result.stdout or ""
