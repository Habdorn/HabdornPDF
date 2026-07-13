from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import APP_NAME, APP_WEBSITE, DEVELOPMENT_VERSION_LABEL
from dialogs.common import BaseDialog, open_external_url
from dialogs.third_party_dialog import ThirdPartyNoticesDialog


class AboutDialog(BaseDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(f"Acerca de {APP_NAME}", parent, (540, 430))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)

        heading = QLabel(APP_NAME)
        heading.setProperty("role", "heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        version = QLabel(DEVELOPMENT_VERSION_LABEL)
        version.setProperty("role", "muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        description = QLabel(
            "Editor visual local para crear, reorganizar y exportar documentos "
            "PDF.\n\nCreado por Habdorn.\n\nLos documentos se procesan "
            "localmente. Habdorn PDF no sube archivos a servidores externos.\n\n"
            "Los proyectos .hpdf conservan el documento editable y sus recursos.\n\n"
            "Iconos Lucide, distribuidos bajo licencia ISC."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(description, 1)

        action_row = QHBoxLayout()
        website_button = QPushButton("habdorn.com")
        website_button.clicked.connect(
            lambda: open_external_url(self, APP_WEBSITE, "el sitio web de Habdorn")
        )
        notices_button = QPushButton("Avisos de terceros")
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
        ThirdPartyNoticesDialog(self).exec()
