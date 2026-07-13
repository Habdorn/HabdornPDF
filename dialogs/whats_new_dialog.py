from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.constants import APP_NAME
from dialogs.common import BaseDialog
from i18n import Translator


class WhatsNewDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        translator: Optional[Translator] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.whats_new.title"),
            parent,
            (560, 410),
            active_translator,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(
            self.tr(
                "dialog.whats_new.heading",
                app=APP_NAME,
                version=self.tr("version.development"),
            )
        )
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        content = QLabel(self.tr("dialog.whats_new.content"))
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(content, 1)
        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
