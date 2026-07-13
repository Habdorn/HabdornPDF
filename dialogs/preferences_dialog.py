from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dialogs.common import BaseDialog
from app.constants import APP_NAME
from i18n import Translator, load_saved_locale, save_locale


class PreferencesDialog(BaseDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        translator: Optional[Translator] = None,
        settings: Optional[QSettings] = None,
    ) -> None:
        active_translator = translator or Translator()
        super().__init__(
            active_translator.get("dialog.preferences.title"),
            parent,
            (590, 390),
            active_translator,
        )
        self.settings = settings or QSettings()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._general_tab(),
            self.tr("dialog.preferences.general_tab"),
        )
        self.tabs.addTab(
            self._language_tab(),
            self.tr("dialog.preferences.language_tab"),
        )
        self.tabs.addTab(
            self._appearance_tab(),
            self.tr("dialog.preferences.appearance_tab"),
        )
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            self.tr("common.save")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self.tr("common.cancel")
        )
        buttons.accepted.connect(self._save_preferences)
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
            self.tr("dialog.preferences.general_note")
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)
        return tab

    def _language_tab(self) -> QWidget:
        tab, layout = self._tab_with_layout()
        form = QFormLayout()
        self.language_combo = QComboBox()
        self.language_combo.addItem(
            self.tr("dialog.preferences.language_es"),
            "es",
        )
        self.language_combo.addItem(
            self.tr("dialog.preferences.language_en"),
            "en",
        )
        saved_locale = load_saved_locale(self.settings)
        self.language_combo.setCurrentIndex(
            self.language_combo.findData(saved_locale)
        )
        form.addRow(
            self.tr("dialog.preferences.language_label"),
            self.language_combo,
        )
        layout.addLayout(form)
        note = QLabel(
            self.tr("dialog.preferences.language_note")
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _appearance_tab(self) -> QWidget:
        tab, layout = self._tab_with_layout()
        form = QFormLayout()
        current_theme = QLabel(self.tr("dialog.preferences.dark_theme"))
        form.addRow(self.tr("dialog.preferences.theme_label"), current_theme)
        layout.addLayout(form)
        note = QLabel(self.tr("dialog.preferences.appearance_note"))
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _save_preferences(self) -> None:
        selected_locale = self.language_combo.currentData()
        previous_locale = load_saved_locale(self.settings)
        if selected_locale != previous_locale:
            save_locale(selected_locale, self.settings)
            QMessageBox.information(
                self,
                APP_NAME,
                self.tr("dialog.preferences.restart_notice"),
            )
        self.accept()
