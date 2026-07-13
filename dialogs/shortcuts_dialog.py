from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from dialogs.common import BaseDialog
from i18n import Translator


class ShortcutsDialog(BaseDialog):
    SHORTCUTS = (
        ("Ctrl+N", "shortcut.new_project"),
        ("Ctrl+O", "shortcut.open_project"),
        ("Ctrl+S", "shortcut.save_project"),
        ("Ctrl+Shift+S", "shortcut.save_as"),
        ("Ctrl+Alt+O", "shortcut.add_pdf"),
        ("Ctrl+Shift+E", "shortcut.export_pdf"),
        ("Ctrl+Z", "shortcut.undo"),
        ("Ctrl+Y / Ctrl+Shift+Z", "shortcut.redo"),
        ("Ctrl+Shift+L", "shortcut.rotate_left"),
        ("Ctrl+Shift+R", "shortcut.rotate_right"),
        ("shortcut.delete_keys", "shortcut.delete_image"),
        ("shortcut.zoom_keys", "shortcut.zoom"),
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        translator: Optional[Translator] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.shortcuts.title"),
            parent,
            (570, 470),
            active_translator,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        heading = QLabel(self.tr("dialog.shortcuts.title"))
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(9)
        for row, (shortcut_key, description_key) in enumerate(self.SHORTCUTS):
            shortcut = (
                self.tr(shortcut_key)
                if shortcut_key.startswith("shortcut.")
                else shortcut_key
            )
            shortcut_label = QLabel(shortcut)
            shortcut_label.setStyleSheet("font-family: Consolas; font-weight: 600;")
            grid.addWidget(shortcut_label, row, 0)
            grid.addWidget(QLabel(self.tr(description_key)), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
