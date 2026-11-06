# repo_checker

A Linux desktop app (PyQt6) that watches a list of git repositories, fetches
them on an interval, and **fast-forward pulls automatically** when it is
safe. When a pull is not possible (dirty working tree, diverged branch,
fetch/auth error), it sends a desktop notification and color-codes the tray
icon.

## Features

- Tray icon (green / orange / red / gray-paused) with context menu
- Main window with per-repo status table and activity log
- Automatic `--ff-only` fast-forward pulls, only when the working tree is clean
- Desktop notifications on failures, on pulls blocked, and (optionally) on success
- Configurable global / per-repo check intervals and per-repo auto pull toggle
- Single instance guard, hide-to-tray on close, optional login autostart

## Run

```bash
pip install -e .            # or: pipx install .
repo-checker
```

Requirements: Python 3.11+, git on PATH, a StatusNotifier/AppIndicator
tray host (KDE out of the box; GNOME needs an AppIndicator extension).

## Configuration

`~/.config/repo_checker/config.toml` (created on first run):

```toml
[general]
interval_minutes = 15
auto_pull = true
notify_on_failure = true
notify_on_success = true
notify_on_update_available = false
start_minimized = true

[[repos]]
path = "~/Projects/foo"
# branch = "main"           # optional; defaults to the checked out branch
# auto_pull = true          # optional per-repo override
# interval_minutes = 5      # optional per-repo override
```

Repos can also be added/removed via the window's *Add repository...*
toolbar action with a folder picker.

## How auto pull stays safe

1. `git fetch` (non-interactive; credential prompts fail fast instead of hanging)
2. Inspect `<branch>@{upstream}` ahead/behind counts
3. Pull only if working tree is clean AND the branch is a strict descendant
   of upstream (`merge-base --is-ancestor`)
4. Otherwise: status becomes *blocked* and you get one notification
   (on the transition, not on every poll)

## State directory

Logs: `~/.local/state/repo_checker/repo_checker.log`
