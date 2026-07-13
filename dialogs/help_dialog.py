from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import APP_WEBSITE
from dialogs.common import BaseDialog, open_external_url
from dialogs.shortcuts_dialog import ShortcutsDialog


class HelpDialog(BaseDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Ayuda de Habdorn PDF", parent, (610, 440))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel("Ayuda de Habdorn PDF")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        content = QLabel(
            "Habdorn PDF permite crear, reorganizar y exportar documentos PDF "
            "de forma local.\n\n"
            "Primeros pasos:\n\n"
            "1. Añade un PDF, una imagen o una página en blanco.\n"
            "2. Reordena las páginas arrastrando las miniaturas.\n"
            "3. Inserta imágenes sobre una página si lo necesitas.\n"
            "4. Guarda el proyecto como archivo .hpdf para continuar después.\n"
            "5. Exporta el documento final como PDF.\n\n"
            "Los proyectos .hpdf incluyen internamente los archivos utilizados, "
            "por lo que pueden seguir funcionando aunque los originales ya no "
            "estén disponibles."
        )
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(content, 1)

        action_row = QHBoxLayout()
        shortcuts_button = QPushButton("Atajos de teclado")
        shortcuts_button.clicked.connect(self._show_shortcuts)
        website_button = QPushButton("Sitio web de Habdorn")
        website_button.clicked.connect(
            lambda: open_external_url(self, APP_WEBSITE, "el sitio web de Habdorn")
        )
        action_row.addWidget(shortcuts_button)
        action_row.addWidget(website_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()
