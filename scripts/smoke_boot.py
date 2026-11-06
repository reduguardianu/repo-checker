"""Smoke test: boot the whole app offscreen and run one full check cycle.

Run with:  QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/smoke_boot.py <repo-path>
"""

from __future__ import annotations

import os
import sys
import tempfile

# Use a private config/state location so the test never touches real user data.
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="rc-cfg-"))
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp(prefix="rc-state-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from repo_checker import config as config_mod  # noqa: E402
from repo_checker import notifier  # noqa: E402
from repo_checker.models import RepoConfig, expand_path  # noqa: E402
from repo_checker.monitor import Monitor  # noqa: E402

_sent_notify = notifier.notify
sent = []
notifier.notify = lambda summary, body="", urgency="normal": sent.append((summary, body))

# Prepare a state where the repo is BEHIND upstream: push an extra commit
# from a throwaway clone, so the app must fast-forward pull it.
import subprocess  # noqa: E402

remote = subprocess.run(
    ["git", "-C", sys.argv[1], "remote", "get-url", "origin"],
    capture_output=True, text=True, check=True,
).stdout.strip()
pusher = tempfile.mkdtemp(prefix="rc-push-")
subprocess.run(["git", "clone", remote, pusher], capture_output=True, check=True,
               env=os.environ | {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
with open(os.path.join(pusher, "remote_change.txt"), "w") as fh:
    fh.write("new\n")
subprocess.run(["git", "-C", pusher, "add", "."], capture_output=True, check=True)
subprocess.run(["git", "-C", pusher, "commit", "-m", "two"], capture_output=True, check=True,
               env=os.environ | {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
subprocess.run(["git", "-C", pusher, "push"], capture_output=True, check=True)

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

cfg = config_mod.load()
cfg.repos = [RepoConfig(path=sys.argv[1])]
config_mod.save(cfg)

monitor = Monitor(cfg)
from repo_checker.tray import Tray  # noqa: E402
from repo_checker.main_window import MainWindow  # noqa: E402

tray = Tray(monitor, cfg)
window = MainWindow(monitor, tray_available=False)

updates = []
monitor.updated.connect(lambda name: updates.append((name, monitor.state(name).status)))
monitor.log_changed.connect(lambda name: print("LOG:", *monitor.log_lines(name), sep="\n  "))

results = []

def finish():
    name = cfg.repos[0].display_name
    state = monitor.state(name)
    results.append((state.status, state.behind, state.ahead, state.dirty, state.message))
    print("STATE:", state.status, "behind", state.behind, "ahead", state.ahead, "dirty", state.dirty)
    print("MSG:", state.message)
    print("SUMMARY:", monitor.summary())
    print("OVERALL:", monitor.overall_status())
    print("NOTIFICATIONS:", sent)
    print("TRAY ICON REFRESH OK:", tray.icon() is not None)
    window.refresh()
    print("WINDOW REFRESH OK")
    app.quit()

QTimer.singleShot(100, monitor.check_all)
QTimer.singleShot(3500, finish)
app.exec()

status, behind, ahead, dirty, message = results[0]
assert status == "ok", status
assert behind == 0 and ahead == 0, (behind, ahead)
assert not dirty
assert sent, "no notifications fired (on-success expected)"
print("PULL SCENARIO OK")

# ---------------------------------------------------------------------
# Scenario 2: dirty working tree + upstream commit -> pull must be
# blocked and a failure notification must fire.

sent.clear()
results.clear()

commit_env = os.environ | {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
pusher2 = tempfile.mkdtemp(prefix="rc-push2-")
subprocess.run(["git", "clone", remote, pusher2], capture_output=True, check=True)
with open(os.path.join(pusher2, "remote_change2.txt"), "w") as fh:
    fh.write("more\n")
subprocess.run(["git", "-C", pusher2, "add", "."], capture_output=True, check=True)
subprocess.run(["git", "-C", pusher2, "commit", "-m", "three"], capture_output=True, check=True,
               env=commit_env)
subprocess.run(["git", "-C", pusher2, "push"], capture_output=True, check=True)
# dirty the monitored working tree non-interactively
path_repo = expand_path(sys.argv[1])
with open(os.path.join(path_repo, "dirty.txt"), "w") as fh:
    fh.write("local\n")

# Shrink the backoff-free next check so the second cycle runs quickly.
monitor._next_check[cfg.repos[0].display_name] = 0.0
from repo_checker.models import STATUS_BLOCKED  # noqa: E402
monitor.check_all()

def finish2():
    state = monitor.state(cfg.repos[0].display_name)
    results.append(state)
    print("STATE2:", state.status, "behind", state.behind)
    print("MSG2:", state.message)
    print("NOTIFICATIONS2:", sent)
    print("OVERALL2:", monitor.overall_status())
    app.quit()

QTimer.singleShot(3000, finish2)
app.exec()

state = results.pop()
assert state.status == STATUS_BLOCKED, state.status
assert state.behind == 1, state.behind
assert sent, "blocked transition should notify"
assert "local changes" in state.message.lower(), state.message
assert set(sent[0][0].split(" - ")[:1]) == {"Repo Checker"}
print("BLOCKED SCENARIO OK")

print("SMOKE OK")
