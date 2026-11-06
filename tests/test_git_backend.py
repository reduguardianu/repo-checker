"""Tests for git_backend and config against real throwaway repos."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from repo_checker import config as config_mod
from repo_checker import git_backend as git

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def g(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=os.environ | GIT_IDENTITY,
    )


def commit_file(repo: Path, filename: str, content: str, msg: str) -> None:
    (repo / filename).write_text(content + "\n")
    g("add", ".", cwd=repo)
    g("commit", "-m", msg, cwd=repo)


def make_work_repo(tmp_path: Path) -> Path:
    """A 'work' clone of a tiny bare 'origin'; a second clone can push."""
    origin = tmp_path / "origin.git"
    g("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    work = tmp_path / "work"
    g("init", "--initial-branch=main", str(work), cwd=tmp_path)
    g("remote", "add", "origin", str(origin), cwd=work)
    commit_file(work, "file.txt", "one", "one")
    g("push", "-u", "origin", "main", cwd=work)
    return work


@pytest.fixture()
def work_repo(tmp_path: Path) -> Path:
    """Fixture variant if a test requests `work_repo` directly."""
    return make_work_repo(tmp_path)


def push_clone_of(tmp_path: Path, *, name: str = "pusher") -> Path:
    """Create a second clone of work's origin that pushes a new commit."""
    work = tmp_path / "work"
    origin = tmp_path / "origin.git"
    pusher = tmp_path / name
    g("clone", str(origin), str(pusher), cwd=tmp_path)
    commit_file(pusher, "other.txt", "two", "two")
    g("push", cwd=pusher)
    _ = work
    return pusher


# ----------------------------------------------------------------------
# git backend


def test_upstream_commit_detected_and_pulled(tmp_path: Path) -> None:
    work = make_work_repo(tmp_path)
    push_clone_of(tmp_path)

    assert git.is_work_tree(str(work))
    assert not git.is_dirty(str(work))
    branch = git.current_branch(str(work))
    assert branch == "main"
    up = git.upstream(str(work), branch)
    assert up == "origin/main"
    assert git.ahead_behind(str(work), branch, up) == (0, 0)

    git.fetch(str(work))
    assert git.ahead_behind(str(work), branch, up) == (0, 1)
    assert git.is_ancestor(str(work), branch, up)

    git.pull_ff(str(work))
    assert (work / "other.txt").exists()
    assert git.ahead_behind(str(work), branch, up) == (0, 0)


def test_dirty_tree_detected(tmp_path: Path) -> None:
    work = make_work_repo(tmp_path)
    (work / "new.txt").write_text("dirty\n")
    assert git.is_dirty(str(work))


def test_pull_ff_blocked_when_diverged(tmp_path: Path) -> None:
    work = make_work_repo(tmp_path)
    commit_file(work, "local.txt", "local", "local")
    push_clone_of(tmp_path)

    branch = git.current_branch(str(work))
    up = git.upstream(str(work), branch)
    git.fetch(str(work))
    assert git.ahead_behind(str(work), branch, up) == (1, 1)
    assert not git.is_ancestor(str(work), branch, up)
    with pytest.raises(git.GitError):
        git.pull_ff(str(work))


def test_missing_upstream_message(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    g("init", "--initial-branch=main", str(repo), cwd=tmp_path)
    commit_file(repo, "a.txt", "a", "a")  # no upstream configured
    with pytest.raises(git.GitError) as excinfo:
        git.upstream(str(repo), "main")
    assert "no upstream" in excinfo.value.detail.lower()


def test_detached_head(tmp_path: Path) -> None:
    work = make_work_repo(tmp_path)
    g("checkout", "--detach", "HEAD", cwd=work)
    assert git.current_branch(str(work)) is None


def test_not_a_git_dir(tmp_path: Path) -> None:
    assert not git.is_work_tree(str(tmp_path))


def test_run_raises_on_bad_path(tmp_path: Path) -> None:
    with pytest.raises(git.GitError):
        git._run(str(tmp_path / "nope"), "status")


# ----------------------------------------------------------------------
# config


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    config_mod.load(path)  # creates default file
    assert path.is_file()

    cfg = config_mod.load(path)
    cfg.repos = [config_mod.RepoConfig(path="~/Projects/foo", branch="main", interval_minutes=5)]
    cfg.interval_minutes = 7
    config_mod.save(cfg, path)

    cfg2 = config_mod.load(path)
    assert cfg2.interval_minutes == 7
    assert len(cfg2.repos) == 1
    repo = cfg2.repos[0]
    assert repo.path == "~/Projects/foo"
    assert repo.branch == "main"
    assert repo.interval_minutes == 5
    assert repo.display_name == "foo"


def test_validate_new_repo_flags_duplicates(tmp_path: Path) -> None:
    cfg = config_mod.AppConfig()
    cfg.repos = [config_mod.RepoConfig(path="/home/x/alpha")]

    # different path, unique name -> fine
    config_mod.validate_new_repo(cfg, config_mod.RepoConfig(path="/home/x/beta"))

    # new dir with an old display name -> rejected
    with pytest.raises(ValueError):
        config_mod.validate_new_repo(cfg, config_mod.RepoConfig(path="/home/x/beta", name="alpha"))

    # same path -> rejected
    with pytest.raises(ValueError):
        config_mod.validate_new_repo(cfg, config_mod.RepoConfig(path="/home/x/alpha"))


def test_display_name() -> None:
    from repo_checker.models import RepoConfig, display_name_for

    assert RepoConfig(path="~/Projects/foo").display_name == "foo"
    assert RepoConfig(path="/tmp/x", name="custom").display_name == "custom"
    assert display_name_for("/tmp/x/") == "x"
