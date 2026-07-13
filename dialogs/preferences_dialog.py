from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dialogs.common import BaseDialog


class PreferencesDialog(BaseDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Preferencias", parent, (590, 390))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._language_tab(), "Idioma")
        tabs.addTab(self._appearance_tab(), "Apariencia")
        layout.addWidget(tabs, 1)

        buttons = self.close_buttons()
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _tab_with_layout() -> tuple[QWidget, QVBoxLayout]:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        return tab, layout

    def _general_tab(self) -> QWidget:
        tab, layout = self._tab_with_layout()
        message = QLabel(
            "Los cambios de preferencias se ampliarán en próximas versiones."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)
        return tab

    def _language_tab(self) -> QWidget:
        tab, layout = self._tab_with_layout()
        form = QFormLayout()
        language = QComboBox()
        language.addItem("Español")
        language.setEnabled(False)
        form.addRow("Idioma de la interfaz", language)
        layout.addLayout(form)
        note = QLabel(
            "El soporte para cambiar el idioma se añadirá en una próxima etapa."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _appearance_tab(self) -> QWidget:
        tab, layout = self._tab_with_layout()
        form = QFormLayout()
        current_theme = QLabel("Oscuro")
        form.addRow("Tema actual", current_theme)
        layout.addLayout(form)
        note = QLabel("Otros temas estarán disponibles en una próxima versión.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab
