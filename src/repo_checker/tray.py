"""QSystemTrayIcon with color-coded status and context menu."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from . import icons
from . import config as config_mod
from .models import STATUS_ERROR, RepoState
from .monitor import Monitor


class Tray(QSystemTrayIcon):
    open_window = pyqtSignal()
    open_settings = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, monitor: Monitor, app_config: config_mod.AppConfig) -> None:
        super().__init__(icons.status_icon(monitor.overall_status()))
        self._monitor = monitor
        self._cfg = app_config
        self._menu = QMenu()
        self.setContextMenu(self._menu)

        monitor.updated.connect(lambda _name: self.refresh())
        monitor.refresh.connect(self.refresh)

        self.setToolTip(f"Repo Checker - {monitor.summary()}")
        self.activated.connect(self._on_activated)

    def refresh(self) -> None:
        self.setIcon(icons.status_icon(self._monitor.overall_status()))
        self.setToolTip(f"Repo Checker - {self._monitor.summary()}")
        self._rebuild_menu()

    def _status_text(self, state: RepoState) -> str:
        parts = []
        if state.behind:
            parts.append(f"v-{state.behind}")
        if state.ahead:
            parts.append(f"^+{state.ahead}")
        if state.dirty:
            parts.append("dirty")
        return ", ".join(parts) or "ok"

    def _rebuild_menu(self) -> None:
        monitor = self._monitor
        menu = self._menu
        menu.clear()

        open_action = menu.addAction("Open window")
        open_action.triggered.connect(self.open_window.emit)  # type: ignore[arg-type]

        check_all = menu.addAction("Check all now")
        check_all.triggered.connect(monitor.check_all)  # type: ignore[arg-type]

        pause = menu.addAction("Pause monitoring")
        pause.setCheckable(True)
        pause.setChecked(monitor.paused)
        pause.toggled.connect(monitor.set_paused)  # type: ignore[arg-type]

        menu.addSeparator()
        repos = monitor.repos()
        if not repos:
            no_repos = menu.addAction("No repositories configured")
            no_repos.setEnabled(False)
        for repo in sorted(repos, key=lambda r: r.display_name):
            state = monitor.state(repo.display_name)
            label = repo.display_name
            if state.status == STATUS_ERROR:
                label += "  [error]"
            elif state.behind or state.ahead or state.dirty:
                label += f"  ({self._status_text(state)})"
            action = menu.addAction(label)
            action.setToolTip(state.message)
            action.triggered.connect(
                lambda _checked=False, name=repo.display_name:
                    monitor.check_now(name)
            )  # type: ignore[arg-type,misc]

        menu.addSeparator()
        settings_action = menu.addAction("Preferences...")
        settings_action.triggered.connect(self.open_settings.emit)  # type: ignore[arg-type]
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)  # type: ignore[arg-type]

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.open_window.emit()
