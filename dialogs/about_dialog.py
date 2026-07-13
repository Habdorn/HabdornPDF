from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import APP_NAME, APP_WEBSITE
from dialogs.common import BaseDialog, open_external_url
from dialogs.third_party_dialog import ThirdPartyNoticesDialog
from i18n import Translator


class AboutDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        translator: Optional[Translator] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.about.title", app=APP_NAME),
            parent,
            (540, 430),
            active_translator,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)

        heading = QLabel(APP_NAME)
        heading.setProperty("role", "heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        version = QLabel(self.tr("version.development"))
        version.setProperty("role", "muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        description = QLabel(self.tr("dialog.about.content"))
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(description, 1)

        action_row = QHBoxLayout()
        website_button = QPushButton(self.tr("dialog.about.website"))
        website_button.clicked.connect(
            lambda: open_external_url(
                self,
                APP_WEBSITE,
                self.tr("link.website_description"),
                self.translator,
            )
        )
        notices_button = QPushButton(self.tr("dialog.third_party.title"))
        notices_button.clicked.connect(self._show_notices)
        action_row.addStretch(1)
        action_row.addWidget(website_button)
        action_row.addWidget(notices_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_notices(self) -> None:
        ThirdPartyNoticesDialog(
            self,
            translator=self.translator,
        ).exec()
