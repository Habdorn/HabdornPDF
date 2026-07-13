from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from app import lucide_resources  # noqa: F401 - registers bundled resources
from dialogs.common import BaseDialog
from i18n import Translator


THIRD_PARTY_RESOURCE = ":/notices/THIRD_PARTY_NOTICES.md"


def load_third_party_notices(
    resource_path: str = THIRD_PARTY_RESOURCE,
    translator: Optional[Translator] = None,
) -> tuple[str, Optional[str]]:
    active_translator = translator or Translator()
    resource = QFile(resource_path)
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        return "", active_translator.get("dialog.third_party.load_error")
    try:
        return bytes(resource.readAll()).decode("utf-8"), None
    except UnicodeDecodeError:
        return "", active_translator.get("dialog.third_party.format_error")
    finally:
        resource.close()


class ThirdPartyNoticesDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        resource_path: str = THIRD_PARTY_RESOURCE,
        translator: Optional[Translator] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.third_party.title"),
            parent,
            (680, 500),
            active_translator,
        )
        self.notice_text, self.load_error = load_third_party_notices(
            resource_path,
            self.translator,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        heading = QLabel(self.tr("dialog.third_party.title"))
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(self.notice_text if not self.load_error else self.load_error)
        layout.addWidget(viewer, 1)
        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
