from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from dialogs.common import BaseDialog


class ShortcutsDialog(BaseDialog):
    SHORTCUTS = (
        ("Ctrl+N", "Nuevo proyecto"),
        ("Ctrl+O", "Abrir proyecto"),
        ("Ctrl+S", "Guardar proyecto"),
        ("Ctrl+Shift+S", "Guardar proyecto como"),
        ("Ctrl+Alt+O", "Añadir PDF"),
        ("Ctrl+Shift+E", "Exportar PDF"),
        ("Ctrl+Z", "Deshacer"),
        ("Ctrl+Y / Ctrl+Shift+Z", "Rehacer"),
        ("Ctrl+Shift+L", "Rotar página a la izquierda"),
        ("Ctrl+Shift+R", "Rotar página a la derecha"),
        ("Supr / Retroceso", "Eliminar imagen seleccionada"),
        ("Ctrl + rueda", "Cambiar zoom"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Atajos de teclado", parent, (570, 470))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        heading = QLabel("Atajos de teclado")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(9)
        for row, (shortcut, description) in enumerate(self.SHORTCUTS):
            shortcut_label = QLabel(shortcut)
            shortcut_label.setStyleSheet("font-family: Consolas; font-weight: 600;")
            grid.addWidget(shortcut_label, row, 0)
            grid.addWidget(QLabel(description), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
