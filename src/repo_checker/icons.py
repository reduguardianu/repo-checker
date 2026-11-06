"""Runtime-generated tray/status icons (no image asset files needed)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from .models import (
    STATUS_BEHIND,
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNKNOWN,
)

_COLORS = {
    STATUS_UNKNOWN: "#94a3b8",
    STATUS_OK: "#22c55e",
    STATUS_BEHIND: "#f59e0b",
    STATUS_BLOCKED: "#f59e0b",
    STATUS_ERROR: "#ef4444",
    "paused": "#6b7280",
}

_cache: dict[str, QIcon] = {}


def status_hex(status: str) -> str:
    """Hex color used for UI coloring of a given status."""
    if status == "paused":
        return _COLORS["paused"]
    return _COLORS.get(status, _COLORS[STATUS_UNKNOWN])


def render(status: str, size: int = 64) -> QPixmap:
    """Render one status dot at an arbitrary pixel size.

    Also used to write the hicolor PNG for the .desktop launcher entry.
    """
    color = _COLORS.get(status, _COLORS[STATUS_UNKNOWN])
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#1e293b"), size * 5 / 64))
        painter.setBrush(QColor(color))
        margin = round(size * 8 / 64)
        inner = size - 2 * margin
        painter.drawEllipse(margin, margin, inner, inner)
        painter.setPen(QPen(QColor("#ffffff"), round(size * 6 / 64)))
        if status == "paused":
            painter.drawLine(int(size * 26 / 64), int(size * 24 / 64),
                             int(size * 26 / 64), int(size * 40 / 64))
            painter.drawLine(int(size * 38 / 64), int(size * 24 / 64),
                             int(size * 38 / 64), int(size * 40 / 64))
        elif status == STATUS_ERROR:
            painter.drawLine(int(size * 32 / 64), int(size * 20 / 64),
                             int(size * 32 / 64), int(size * 34 / 64))
            painter.drawLine(int(size * 32 / 64), int(size * 39 / 64),
                             int(size * 32 / 64), int(size * 43 / 64))
    finally:
        painter.end()
    return pm


def status_icon(status: str) -> QIcon:
    """A filled dot with a dark ring, colored by status (gray when paused)."""
    if status in _cache:
        return _cache[status]
    icon = QIcon(render(status, 64))
    _cache[status] = icon
    return icon
