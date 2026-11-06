"""Main application window: repo table, toolbar, per-repo activity log."""

from __future__ import annotations

import os

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import config as config_mod
from .branch_cache import BranchCache
from .icons import status_hex
from .models import (
    STATUS_TEXT,
    RepoConfig,
    relative_time,
)
from .monitor import Monitor

COLUMNS = [
    "Repository",
    "Branch",
    "Status",
    "Behind",
    "Ahead",
    "Dirty",
    "Last check",
    "Last pull",
]


class AddRepoDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add repository")
        self.setMinimumWidth(430)
        self.repo: RepoConfig | None = None

        form = QFormLayout()
        self.path_edit = QLineEdit(self)
        browse = QPushButton("Browse...", self)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("Path:", path_row)

        self.branch_edit = QLineEdit(self)
        self.branch_edit.setPlaceholderText("(track the current branch / HEAD)")
        form.addRow("Branch:", self.branch_edit)

        self.auto_pull = QCheckBox("Auto pull (fast-forward only)", self)
        self.auto_pull.setChecked(True)
        form.addRow(self.auto_pull)

        self.interval = QSpinBox(self)
        self.interval.setRange(0, 1440)
        self.interval.setSuffix(" min")
        self.interval.setSpecialValueText("(global)")
        form.addRow("Interval:", self.interval)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_ok(self) -> None:
        path = os.path.expanduser(self.path_edit.text().strip())
        if not path:
            QMessageBox.warning(self, "Add repository", "Please pick a repository path.")
            return
        self.repo = RepoConfig(
            path=path,
            name="",
            branch=self.branch_edit.text().strip(),
            auto_pull=self.auto_pull.isChecked(),
            interval_minutes=self.interval.value(),
        )
        super().accept()

    def _browse(self) -> None:
        start = self.path_edit.text().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(self, "Repository path", start)
        if chosen:
            self.path_edit.setText(chosen)


class MainWindow(QMainWindow):
    settings_opened = pyqtSignal()  # emitted when Preferences opens

    def __init__(self, monitor: Monitor, tray_available: bool = True) -> None:
        super().__init__()
        self._monitor = monitor
        self._tray_available = tray_available
        self._hide_tip_shown = False
        self._branch_cache = BranchCache()
        self._branch_cache.callback = self.refresh

        self.setWindowTitle("Repo Checker")
        self.resize(860, 520)

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 2)

        layout.addWidget(QLabel("Activity log", self), 0)
        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(170)
        layout.addWidget(self.log_view, 0)

        self.setCentralWidget(central)
        self._build_toolbar()
        self._connect_signals()
        self.refresh()

        # Refresh relative times ("5 min ago") periodically.
        self._clock = QTimer(self)
        self._clock.timeout.connect(self.refresh)
        self._clock.start(30_000)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("main", self)
        self.addToolBar(toolbar)

        check_action = toolbar.addAction("Check all")
        check_action.triggered.connect(self._monitor.check_all)

        toolbar.addAction("Add repository...").triggered.connect(self._add_repo)
        self._remove_action = toolbar.addAction("Remove")
        self._remove_action.triggered.connect(self._remove_selected)
        self._open_action = toolbar.addAction("Open folder")
        self._open_action.triggered.connect(self._open_folder)
        toolbar.addSeparator()
        toolbar.addAction("Preferences...").triggered.connect(self._open_settings)

    def _connect_signals(self) -> None:
        self._monitor.refresh.connect(self.refresh)
        self._monitor.updated.connect(lambda _name: self.refresh())
        self._monitor.log_changed.connect(self._on_log_changed)
        self.table.itemSelectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        repos = sorted(self._monitor.repos(), key=lambda r: r.display_name)
        selected = self.selected_repo()
        table = self.table
        table.setRowCount(len(repos))
        for row, repo in enumerate(repos):
            state = self._monitor.state(repo.display_name)
            values = [
                repo.display_name,
                self._branch_cache.get(repo),
                STATUS_TEXT.get(state.status, state.status),
                state.behind or "",
                state.ahead or "",
                "yes" if state.dirty else "",
                relative_time(state.last_check),
                relative_time(state.last_pull),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setToolTip(state.message or None)
                if col == 2 and (color := status_hex(state.status)):
                    item.setForeground(QBrush(QColor(color)))
                table.setItem(row, col, item)
        if selected:
            for row, repo in enumerate(repos):
                if repo.display_name == selected:
                    table.selectRow(row)
                    break
        self._on_selection()

    def selected_repo(self) -> str | None:
        selection = self.table.selectionModel()
        if not selection:
            return None
        rows = selection.selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.text() if item else None

    # ------------------------------------------------------------------
    def _on_selection(self) -> None:
        selected = self.selected_repo()
        has_selection = bool(selected)
        self._remove_action.setEnabled(has_selection)
        self._open_action.setEnabled(has_selection)
        self._show_log(selected)

    def _show_log(self, name: str | None) -> None:
        if name:
            self.log_view.setPlainText("\n".join(self._monitor.log_lines(name)))
        else:
            self.log_view.setPlainText("")
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_log_changed(self, name: str) -> None:
        if name == self.selected_repo():
            self._show_log(name)

    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dlg = SettingsDialog(self._monitor, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings_opened.emit()
            self.refresh()

    def _add_repo(self) -> None:
        dlg = AddRepoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.repo:
            return
        repo = dlg.repo
        try:
            config_mod.validate_new_repo(self._monitor._app_cfg, repo)
        except ValueError as exc:
            QMessageBox.warning(self, "Add repository", str(exc))
            return
        self._monitor.add_repo(repo)
        self.refresh()

    def _remove_selected(self) -> None:
        name = self.selected_repo()
        if not name:
            return
        confirm = QMessageBox.question(
            self,
            "Remove repository",
            f"Stop monitoring {name!r}?\n\nThe repository itself is not touched.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._monitor.remove_repo(name)
            self.refresh()

    def _open_folder(self) -> None:
        name = self.selected_repo()
        if not name:
            return
        for repo in self._monitor.repos():
            if repo.display_name == name:
                QDesktopServices.openUrl(QUrl.fromLocalFile(repo.path))
                return

    # ------------------------------------------------------------------
    def show_and_activate(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Hide to tray on close; real quit only happens via tray menu."""
        if self._tray_available:
            event.ignore()
            self.hide()
            if not self._hide_tip_shown:
                from . import notifier

                notifier.notify(
                    "Repo Checker",
                    "Still running in the system tray. Use the tray menu to quit.",
                )
                self._hide_tip_shown = True
        else:
            event.accept()
