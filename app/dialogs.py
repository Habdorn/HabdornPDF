from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QFile, QIODevice, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import lucide_resources  # noqa: F401 - registers bundled resources
from app.constants import (
    APP_NAME,
    APP_WEBSITE,
    DEVELOPMENT_VERSION_LABEL,
    UI_COLORS,
)


THIRD_PARTY_RESOURCE = ":/notices/THIRD_PARTY_NOTICES.md"


def _dialog_style() -> str:
    colors = UI_COLORS
    return f"""
        QDialog {{ background: {colors['window']}; color: {colors['text']}; }}
        QLabel, QGroupBox {{ color: {colors['text']}; }}
        QLabel[role="muted"] {{ color: {colors['muted']}; }}
        QLabel[role="heading"] {{ font-size: 19px; font-weight: 700; }}
        QLabel[role="link"] {{ color: {colors['accent_hover']}; }}
        QTabWidget::pane {{
            background: {colors['panel']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
        }}
        QTabBar::tab {{
            background: {colors['surface']};
            border: 1px solid {colors['border']};
            padding: 8px 14px;
        }}
        QTabBar::tab:selected {{
            background: {colors['surface_hover']};
            border-bottom-color: {colors['accent']};
        }}
        QPushButton, QComboBox {{
            background: {colors['surface']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 5px;
            padding: 7px 12px;
        }}
        QPushButton:hover {{ border-color: {colors['accent']}; }}
        QPushButton:pressed {{ background: {colors['surface_hover']}; }}
        QPlainTextEdit {{
            background: {colors['panel']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 6px;
            padding: 8px;
        }}
    """


class BaseDialog(QDialog):
    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        minimum_size: tuple[int, int] = (480, 320),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(*minimum_size)
        self.setModal(True)
        self.setStyleSheet(_dialog_style())

    @staticmethod
    def close_buttons() -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        return buttons


def open_external_url(
    parent: Optional[QWidget],
    url: str,
    description: str,
) -> bool:
    if QDesktopServices.openUrl(QUrl(url)):
        return True
    QMessageBox.warning(
        parent,
        APP_NAME,
        f"No se pudo abrir {description}.\n\n{url}",
    )
    return False


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
