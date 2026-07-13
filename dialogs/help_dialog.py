from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import APP_WEBSITE
from dialogs.common import BaseDialog, open_external_url
from dialogs.shortcuts_dialog import ShortcutsDialog
from i18n import Translator


class HelpDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        translator: Optional[Translator] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.help.title"),
            parent,
            (610, 440),
            active_translator,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(self.tr("dialog.help.title"))
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        content = QLabel(self.tr("dialog.help.content"))
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(content, 1)

        action_row = QHBoxLayout()
        shortcuts_button = QPushButton(self.tr("action.shortcuts"))
        shortcuts_button.clicked.connect(self._show_shortcuts)
        website_button = QPushButton(self.tr("action.website"))
        website_button.clicked.connect(
            lambda: open_external_url(
                self,
                APP_WEBSITE,
                self.tr("link.website_description"),
                self.translator,
            )
        )
        action_row.addWidget(shortcuts_button)
        action_row.addWidget(website_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self, self.translator).exec()
