from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QWidget,
)

from app.constants import APP_NAME, UI_COLORS


def _dialog_style() -> str:
    colors = UI_COLORS
    return f"""
        QDialog {{ background: {colors['window']}; color: {colors['text']}; }}
        QLabel, QGroupBox {{ color: {colors['text']}; }}
        QLabel[role="muted"] {{ color: {colors['muted']}; }}
        QLabel[role="heading"] {{ font-size: 19px; font-weight: 700; }}
        QLabel[role="link"] {{ color: {colors['accent_hover']}; }}
        QTabWidget::pane {{
            background: {colors['panel']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
        }}
        QTabBar::tab {{
            background: {colors['surface']};
            border: 1px solid {colors['border']};
            padding: 8px 14px;
        }}
        QTabBar::tab:selected {{
            background: {colors['surface_hover']};
            border-bottom-color: {colors['accent']};
        }}
        QPushButton, QComboBox {{
            background: {colors['surface']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 5px;
            padding: 7px 12px;
        }}
        QPushButton:hover {{ border-color: {colors['accent']}; }}
        QPushButton:pressed {{ background: {colors['surface_hover']}; }}
        QPlainTextEdit {{
            background: {colors['panel']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 8px;
        }}
    """


class BaseDialog(QDialog):
    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        minimum_size: tuple[int, int] = (480, 320),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(*minimum_size)
        self.setModal(True)
        self.setStyleSheet(_dialog_style())

    @staticmethod
    def close_buttons() -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        return buttons


def open_external_url(
    parent: Optional[QWidget],
    url: str,
    description: str,
) -> bool:
    if QDesktopServices.openUrl(QUrl(url)):
        return True
    QMessageBox.warning(
        parent,
        APP_NAME,
        f"No se pudo abrir {description}.\n\n{url}",
    )
    return False
