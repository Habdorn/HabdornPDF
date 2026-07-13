from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.constants import APP_NAME, DEVELOPMENT_VERSION_LABEL
from dialogs.common import BaseDialog


class WhatsNewDialog(BaseDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Novedades", parent, (560, 410))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(f"{APP_NAME} — {DEVELOPMENT_VERSION_LABEL}")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        content = QLabel(
            "Novedades principales:\n\n"
            "• Proyectos editables y portables .hpdf.\n"
            "• Assets embebidos que no dependen de los archivos originales.\n"
            "• Guardado y apertura segura de proyectos.\n"
            "• Historial estable de Deshacer y Rehacer.\n"
            "• Mini-ribbon moderna con iconos Lucide.\n"
            "• Nueva interfaz visual, pantalla inicial y estados vacíos.\n"
            "• Exportación PDF local y sin subir documentos a internet."
        )
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(content, 1)
        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
