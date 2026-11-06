"""Application entry point: wires config, monitor, tray and main window."""

from __future__ import annotations

import logging
import os
import sys
import tempfile

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from . import config as config_mod
from . import icons
from .config import AppConfig, STATE_DIR, ensure_state_dir


def _setup_logging() -> None:
    ensure_state_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(STATE_DIR / "repo_checker.log", encoding="utf-8"),
        ],
    )


def _single_instance_guard(app: QApplication) -> bool:
    """True if we got the lock; False if another instance already runs."""
    # QLockFile lives in QtCore as of Qt 6.
    from PyQt6.QtCore import QLockFile

    lock_path = os.path.join(
        tempfile.gettempdir(), f"repo-checker-{os.getuid()}.lock"
    )
    lock = QLockFile(lock_path)
    if not lock.tryLock(100):
        return False
    app.setProperty("repo_checker_lock", lock)  # keep reference alive
    return True


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    app = QApplication(argv or sys.argv)
    app.setApplicationName(config_mod.APP_NAME)
    app.setApplicationDisplayName("Repo Checker")
    app.setQuitOnLastWindowClosed(False)

    if not _single_instance_guard(app):
        QMessageBox.information(
            QWidget(),
            "Repo Checker",
            "Repo Checker is already running (check your system tray).",
        )
        return 0

    try:
        cfg: AppConfig = config_mod.load()
    except RuntimeError as exc:
        QMessageBox.critical(QWidget(), "Repo Checker", str(exc))
        return 1

    # Imported late so a display-less import of repo_checker stays possible.
    from .main_window import MainWindow
    from .monitor import Monitor
    from .tray import Tray

    monitor = Monitor(cfg)
    tray_available = _tray_available()
    if not tray_available:
        logging.getLogger(__name__).warning(
            "No system tray available; keep the main window open instead."
        )
    tray = Tray(monitor, cfg)

    window = MainWindow(monitor, tray_available=tray_available)
    window.setWindowIcon(icons.status_icon("ok"))

    # Wiring
    tray.open_window.connect(window.show_and_activate)
    tray.open_settings.connect(window._open_settings)
    tray.quit_requested.connect(app.quit)
    monitor.refresh.connect(lambda: tray.refresh())
    tray.refresh()

    if not cfg.start_minimized or not cfg.repos or not tray_available:
        window.show_and_activate()
    tray.show()

    app.aboutToQuit.connect(monitor.shutdown)
    exit_code = app.exec()
    logging.getLogger(__name__).info("exit %s", exit_code)
    return exit_code


def _tray_available() -> bool:
    from PyQt6.QtWidgets import QSystemTrayIcon

    return QSystemTrayIcon.isSystemTrayAvailable()


if __name__ == "__main__":
    raise SystemExit(main())
