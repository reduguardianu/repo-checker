"""Settings dialog editing the shared AppConfig."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from . import autostart
from . import config as config_mod
from .monitor import Monitor


class SettingsDialog(QDialog):
    def __init__(self, monitor: Monitor, parent=None) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self._cfg = monitor._app_cfg  # shared AppConfig instance

        self.setWindowTitle("Repo Checker - Preferences")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.interval = QSpinBox(self)
        self.interval.setRange(1, 1440)
        self.interval.setSuffix(" min")
        self.interval.setValue(self._cfg.interval_minutes)
        form.addRow("Check interval:", self.interval)

        self.auto_pull = QCheckBox("Automatically fast-forward pull (auto pull)", self)
        self.auto_pull.setChecked(self._cfg.auto_pull)
        form.addRow(self.auto_pull)

        self.notify_failure = QCheckBox(
            "Notify when a pull is blocked or fails", self
        )
        self.notify_failure.setChecked(self._cfg.notify_on_failure)
        form.addRow(self.notify_failure)

        self.notify_success = QCheckBox("Notify after successful pulls", self)
        self.notify_success.setChecked(self._cfg.notify_on_success)
        form.addRow(self.notify_success)

        self.notify_updates = QCheckBox(
            "Notify when manual repos have updates", self
        )
        self.notify_updates.setChecked(self._cfg.notify_on_update_available)
        form.addRow(self.notify_updates)

        self.start_minimized = QCheckBox("Start minimized to tray", self)
        self.start_minimized.setChecked(self._cfg.start_minimized)
        form.addRow(self.start_minimized)

        self.autostart = QCheckBox("Launch at login", self)
        self.autostart.setChecked(autostart.enabled())
        form.addRow(self.autostart)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self._cfg.interval_minutes = self.interval.value()
        self._cfg.auto_pull = self.auto_pull.isChecked()
        self._cfg.notify_on_failure = self.notify_failure.isChecked()
        self._cfg.notify_on_success = self.notify_success.isChecked()
        self._cfg.notify_on_update_available = self.notify_updates.isChecked()
        self._cfg.start_minimized = self.start_minimized.isChecked()
        if self.autostart.isChecked():
            autostart.enable()
        else:
            autostart.disable()
        config_mod.save(self._cfg)
        self._monitor.refresh.emit()
        super().accept()
