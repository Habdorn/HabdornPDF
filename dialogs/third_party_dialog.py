from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from app import lucide_resources  # noqa: F401 - registers bundled resources
from dialogs.common import BaseDialog


THIRD_PARTY_RESOURCE = ":/notices/THIRD_PARTY_NOTICES.md"


def load_third_party_notices(
    resource_path: str = THIRD_PARTY_RESOURCE,
) -> tuple[str, Optional[str]]:
    resource = QFile(resource_path)
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        return "", "No se pudieron cargar los avisos de terceros incluidos."
    try:
        return bytes(resource.readAll()).decode("utf-8"), None
    except UnicodeDecodeError:
        return "", "Los avisos de terceros no tienen un formato de texto válido."
    finally:
        resource.close()


class ThirdPartyNoticesDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        resource_path: str = THIRD_PARTY_RESOURCE,
    ) -> None:
        super().__init__("Avisos de terceros", parent, (680, 500))
        self.notice_text, self.load_error = load_third_party_notices(resource_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        heading = QLabel("Avisos de terceros")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(self.notice_text if not self.load_error else self.load_error)
        layout.addWidget(viewer, 1)
        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
