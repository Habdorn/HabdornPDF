from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
from app.constants import A4_PORTRAIT, APP_NAME, UI_COLORS
from commands.overlay_commands import (
    DeleteOverlaysCommand,
    InsertOverlayCommand,
    UpdateOverlayCommand,
)
from commands.page_commands import (
    DeletePagesCommand,
    InsertPagesCommand,
    ReorderPagesCommand,
    RotatePagesCommand,
)
from models.overlay_model import OverlayModel
from models.page_model import PageModel
from services.asset_manager import AssetManager, AssetManagerError
from services.image_utils import rotated_image_stream
from services.pdf_exporter import export_pdf_document
from services.pdf_renderer import (
    fit_rect,
    render_page_pixmap as render_page_pixmap_service,
    rotate_rect,
    rotate_overlay,
    rotated_page_size,
)
from services.project_service import (
    ProjectAssetError,
    ProjectError,
    ProjectFormatError,
    ProjectVersionError,
    load_project,
    save_project,
    utc_now,
)
from widgets.overlay_graphics_item import OverlayGraphicsItem
from widgets.page_list_widget import PageListWidget
from widgets.preview_view import PreviewView
from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QTransform,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self, asset_manager: Optional[AssetManager] = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1420, 860)
        self.setMinimumSize(980, 650)

        self.pages: Dict[str, PageModel] = {}
        self.asset_manager = asset_manager or AssetManager()
        self.current_project_path: Optional[str] = None
        self.project_id = uuid.uuid4().hex
        self.project_created_at = utc_now()
        self.project_modified_at = self.project_created_at
        self.current_page_id: Optional[str] = None
        self.overlay_items: Dict[str, OverlayGraphicsItem] = {}
        self.thumbnail_cache: Dict[str, QPixmap] = {}
        self._changing_selection = False
        self._status_generation = 0
        self._has_temporary_status = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(20)
        self._direct_revision = 0
        self._saved_direct_revision = 0
        self._saved_undo_index = self.undo_stack.index()
        self.is_dirty = False
        self.undo_stack.indexChanged.connect(self._update_dirty_state)
        self.undo_stack.cleanChanged.connect(self._update_dirty_state)
        self.undo_stack.setClean()
        self._create_actions()

        self.scene = QGraphicsScene(self)
        self.preview = PreviewView(self.scene)
        self.preview.delete_pressed.connect(self.delete_selected_overlays)
        self.scene.selectionChanged.connect(self._update_action_states)

        self.page_list = PageListWidget()
        self.page_list.setViewMode(QListView.ViewMode.ListMode)
        self.page_list.setIconSize(QSize(176, 205))
        self.page_list.setFlow(QListView.Flow.TopToBottom)
        self.page_list.setWrapping(False)
        self.page_list.setUniformItemSizes(False)
        self.page_list.setWordWrap(False)
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setMovement(QListWidget.Movement.Snap)
        self.page_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.page_list.setDragEnabled(True)
        self.page_list.setAcceptDrops(True)
        self.page_list.setDropIndicatorShown(True)
        self.page_list.setDragDropOverwriteMode(False)
        self.page_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.page_list.setSpacing(12)
        self.page_list.currentItemChanged.connect(self.on_page_changed)
        self.page_list.itemSelectionChanged.connect(self._update_action_states)
        self.page_list.native_drop_finished.connect(self.on_native_drop_finished)

        left = QWidget()
        left.setObjectName("pagePanel")
        left.setMinimumWidth(270)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 18, 12, 14)
        left_layout.setSpacing(12)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(8)
        title = QLabel("PÁGINAS")
        title.setObjectName("sectionTitle")
        self.page_count_label = QLabel("0 páginas")
        self.page_count_label.setObjectName("pageCount")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.page_count_label)
        left_layout.addLayout(header_layout)

        self.page_list_stack = QStackedWidget()
        self.page_list_stack.setObjectName("pageListStack")
        self.page_list_stack.addWidget(self._build_empty_pages_widget())
        self.page_list_stack.addWidget(self.page_list)
        left_layout.addWidget(self.page_list_stack, 1)

        right = QWidget()
        right.setObjectName("workspacePanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 18, 16, 14)
        right_layout.setSpacing(10)
        self.help_label = QLabel(
            "Arrastra las miniaturas para reordenar · Ctrl + rueda para hacer zoom"
        )
        self.help_label.setWordWrap(True)
        self.help_label.setObjectName("helpText")
        self.help_label.setToolTip(
            "Selecciona una imagen insertada para moverla, redimensionarla o rotarla."
        )
        right_layout.addWidget(self.help_label)

        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.addWidget(self.preview)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setObjectName("previewStack")
        self.preview_stack.addWidget(self._build_welcome_widget())
        self.preview_stack.addWidget(preview_frame)
        right_layout.addWidget(self.preview_stack, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setHandleWidth(1)
        splitter.setSizes([310, 1110])
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menu()
        self._build_undo_shortcuts()
        self._apply_style()
        self.update_window_title()
        self._update_document_ui()

    def _build_empty_pages_widget(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("emptyPages")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)
        title = QLabel("Todavía no hay páginas")
        title.setObjectName("emptyPagesTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(
            "Añade un PDF, una imagen\no una página en blanco."
        )
        description.setObjectName("emptyPagesText")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(description)
        layout.addStretch(1)
        return widget

    def _build_welcome_widget(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("welcomePage")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(2)

        title = QLabel("Crea un documento")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(
            "Añade un PDF, una imagen o una página en blanco\npara comenzar."
        )
        description.setObjectName("welcomeText")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addSpacing(26)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        for text, action in (
            ("Añadir PDF", self.add_pdf_action),
            ("Añadir imagen", self.add_image_page_action),
            ("Página en blanco", self.add_blank_page_action),
        ):
            button = QPushButton(text)
            button.setProperty("role", "welcome")
            button.setMinimumHeight(38)
            button.clicked.connect(
                lambda checked=False, selected_action=action: selected_action.trigger()
            )
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addSpacing(14)

        open_project = QPushButton("Abrir proyecto .hpdf")
        open_project.setProperty("role", "link")
        open_project.setCursor(Qt.CursorShape.PointingHandCursor)
        open_project.clicked.connect(
            lambda checked=False: self.open_project_action.trigger()
        )
        layout.addWidget(open_project, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(3)
        return widget

    def _update_document_ui(self) -> None:
        count = self.page_list.count()
        label = "1 página" if count == 1 else f"{count} páginas"
        self.page_count_label.setText(label)
        has_pages = count > 0
        self.page_list_stack.setCurrentIndex(1 if has_pages else 0)
        self.preview_stack.setCurrentIndex(1 if has_pages else 0)
        self.help_label.setVisible(has_pages)
        self._update_action_states()
        self.update_status_bar()

    def _update_action_states(self) -> None:
        selected_pages = bool(self.page_list.selectedItems())
        has_current_page = (
            self.current_page_id is not None
            and self.current_page_id in self.pages
        )
        selected_overlay = any(
            isinstance(item, OverlayGraphicsItem)
            for item in self.scene.selectedItems()
        )
        self.insert_image_action.setEnabled(has_current_page)
        self.delete_image_action.setEnabled(selected_overlay)
        self.rotate_left_action.setEnabled(selected_pages)
        self.rotate_right_action.setEnabled(selected_pages)
        self.delete_page_action.setEnabled(selected_pages)
        self.export_pdf_action.setEnabled(self.page_list.count() > 0)

    def _show_temporary_status(self, message: str, timeout: int = 4000) -> None:
        self._status_generation += 1
        self._has_temporary_status = True
        generation = self._status_generation
        self.statusBar().showMessage(message)
        QTimer.singleShot(
            timeout,
            lambda: self._restore_status(generation),
        )

    def _restore_status(self, generation: int) -> None:
        if generation != self._status_generation:
            return
        self._has_temporary_status = False
        self.update_status_bar()

    def update_status_bar(self, force: bool = False) -> None:
        if self._has_temporary_status and not force:
            return
        count = self.page_list.count()
        if count == 0:
            message = "Cambios sin guardar" if self.is_dirty else "Listo"
        else:
            current_row = self.page_list.currentRow()
            selection = (
                f"Página {current_row + 1} seleccionada"
                if current_row >= 0
                else "Sin página seleccionada"
            )
            document_state = (
                "Cambios sin guardar"
                if self.is_dirty
                else "Proyecto guardado"
                if self.current_project_path
                else "Listo"
            )
            count_text = "1 página" if count == 1 else f"{count} páginas"
            message = f"{document_state} · {count_text} · {selection}"
        self.statusBar().showMessage(message)

    def set_dirty(self, dirty: bool = True) -> None:
        if self.is_dirty == dirty:
            return
        self.is_dirty = dirty
        self.update_window_title()
        self.update_status_bar()

    def update_window_title(self) -> None:
        suffix = " *" if self.is_dirty else ""
        project_name = (
            Path(self.current_project_path).name
            if self.current_project_path
            else "Sin título"
        )
        self.setWindowTitle(f"{project_name}{suffix} — {APP_NAME}")

    def _update_dirty_state(self, *args) -> None:
        undo_state_matches = (
            self.undo_stack.isClean()
            and self.undo_stack.index() == self._saved_undo_index
        )
        direct_state_matches = (
            self._direct_revision == self._saved_direct_revision
        )
        self.set_dirty(not (undo_state_matches and direct_state_matches))

    def _mark_direct_change(self) -> None:
        self._direct_revision += 1
        self._update_dirty_state()

    def _mark_project_saved_state(self) -> None:
        self._saved_undo_index = self.undo_stack.index()
        self._saved_direct_revision = self._direct_revision
        self.undo_stack.setClean()
        self._update_dirty_state()

    def _create_actions(self) -> None:
        self.undo_action = self.undo_stack.createUndoAction(self, "Deshacer")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_action = self.undo_stack.createRedoAction(self, "Rehacer")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

        self.new_project_action = QAction("Nuevo proyecto", self)
        self.new_project_action.setShortcut(QKeySequence("Ctrl+N"))
        self.new_project_action.triggered.connect(self.new_project)

        self.open_project_action = QAction("Abrir proyecto…", self)
        self.open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_project_action.triggered.connect(self.open_project)

        self.save_project_action = QAction("Guardar proyecto", self)
        self.save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_project_action.triggered.connect(self.save_project)

        self.save_project_as_action = QAction("Guardar proyecto como…", self)
        self.save_project_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_project_as_action.triggered.connect(self.save_project_as)

        self.add_pdf_action = QAction("Añadir PDF", self)
        self.add_pdf_action.setShortcut(QKeySequence("Ctrl+Alt+O"))
        self.add_pdf_action.triggered.connect(self.add_pdfs)
        self.add_pdf_action.setToolTip("Añadir uno o varios archivos PDF")

        self.add_image_page_action = QAction("+ Imagen como página", self)
        self.add_image_page_action.triggered.connect(self.add_images_as_pages)
        self.add_image_page_action.setToolTip("Añadir imágenes como páginas A4")

        self.add_blank_page_action = QAction("+ Página en blanco", self)
        self.add_blank_page_action.triggered.connect(self.add_blank_page)

        self.insert_image_action = QAction("Insertar imagen", self)
        self.insert_image_action.triggered.connect(self.add_overlay_image)

        self.rotate_left_action = QAction("Rotar izquierda", self)
        self.rotate_left_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.rotate_left_action.triggered.connect(
            lambda: self.rotate_selected_pages(-90)
        )

        self.rotate_right_action = QAction("Rotar derecha", self)
        self.rotate_right_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.rotate_right_action.triggered.connect(
            lambda: self.rotate_selected_pages(90)
        )

        self.delete_image_action = QAction("Eliminar imagen", self)
        self.delete_image_action.triggered.connect(self.delete_selected_overlays)

        self.delete_page_action = QAction("Eliminar página", self)
        self.delete_page_action.triggered.connect(self.delete_selected_pages)

        self.export_pdf_action = QAction("Exportar PDF", self)
        self.export_pdf_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.export_pdf_action.triggered.connect(self.export_pdf)

        self.toolbar_undo_action = QAction("Deshacer", self)
        self.toolbar_undo_action.triggered.connect(self.undo_action.trigger)
        self.toolbar_redo_action = QAction("Rehacer", self)
        self.toolbar_redo_action.triggered.connect(self.redo_action.trigger)
        self.undo_action.changed.connect(self._sync_toolbar_undo_redo_actions)
        self.redo_action.changed.connect(self._sync_toolbar_undo_redo_actions)
        self._sync_toolbar_undo_redo_actions()

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Herramientas")
        self.toolbar.setObjectName("mainToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toolbar.setContentsMargins(8, 4, 8, 4)
        self.addToolBar(self.toolbar)

        self._add_toolbar_action(self.toolbar_undo_action)
        self._add_toolbar_action(self.toolbar_redo_action)
        self.toolbar.addSeparator()

        self._add_toolbar_action(self.add_pdf_action, display_text="+ PDF")
        self._add_toolbar_action(self.add_image_page_action)
        self._add_toolbar_action(self.add_blank_page_action)
        self.toolbar.addSeparator()
        self._add_toolbar_action(self.insert_image_action)
        self._add_toolbar_action(self.delete_image_action, "destructive")
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.page_toolbar = QToolBar("Página y salida")
        self.page_toolbar.setObjectName("mainToolbar")
        self.page_toolbar.setMovable(False)
        self.page_toolbar.setFloatable(False)
        self.page_toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.page_toolbar.setContentsMargins(8, 4, 8, 4)
        self.addToolBar(self.page_toolbar)

        self._add_toolbar_action(
            self.rotate_left_action,
            toolbar=self.page_toolbar,
        )
        self._add_toolbar_action(
            self.rotate_right_action,
            toolbar=self.page_toolbar,
        )
        self._add_toolbar_action(
            self.delete_page_action,
            "destructive",
            toolbar=self.page_toolbar,
        )
        self.page_toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.page_toolbar.addWidget(spacer)
        self._add_toolbar_action(
            self.save_project_action,
            "secondary",
            display_text="Guardar",
            toolbar=self.page_toolbar,
        )
        self._add_toolbar_action(
            self.export_pdf_action,
            "primary",
            toolbar=self.page_toolbar,
        )

    def _add_toolbar_action(
        self,
        action: QAction,
        role: str = "normal",
        display_text: Optional[str] = None,
        toolbar: Optional[QToolBar] = None,
    ) -> None:
        target_toolbar = toolbar or self.toolbar
        target_toolbar.addAction(action)
        button = target_toolbar.widgetForAction(action)
        if isinstance(button, QToolButton):
            button.setProperty("role", role)
            button.setMinimumHeight(34)
            button.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
            if display_text:
                button.setText(display_text)

    def _sync_toolbar_undo_redo_actions(self) -> None:
        self.toolbar_undo_action.setText("Deshacer")
        self.toolbar_undo_action.setToolTip(self.undo_action.text())
        self.toolbar_undo_action.setEnabled(self.undo_action.isEnabled())
        self.toolbar_redo_action.setText("Rehacer")
        self.toolbar_redo_action.setToolTip(self.redo_action.text())
        self.toolbar_redo_action.setEnabled(self.redo_action.isEnabled())

    def _build_menu(self) -> None:
        self.file_menu = self.menuBar().addMenu("Archivo")
        file_menu = self.file_menu
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.save_project_action)
        file_menu.addAction(self.save_project_as_action)

        file_menu.addSeparator()
        file_menu.addAction(self.add_pdf_action)
        file_menu.addAction(self.export_pdf_action)

        file_menu.addSeparator()
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.edit_menu = self.menuBar().addMenu("Editar")
        edit_menu = self.edit_menu
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        self.page_menu = self.menuBar().addMenu("Página")
        page_menu = self.page_menu
        page_menu.addAction(self.rotate_left_action)
        page_menu.addAction(self.rotate_right_action)

    def new_project(self) -> None:
        if self.is_dirty and not self._confirm_discard_changes():
            return
        try:
            manager = AssetManager()
        except Exception as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"No se pudo crear un proyecto nuevo.\n\n{exc}",
            )
            return
        self._replace_document(
            manager,
            {},
            [],
            project_path=None,
            project_id=uuid.uuid4().hex,
            created_at=utc_now(),
            modified_at=utc_now(),
        )
        self._update_document_ui()
        self._show_temporary_status("Proyecto nuevo", 4000)

    def open_project(self) -> None:
        if self.is_dirty and not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir proyecto",
            "",
            "Proyecto Habdorn PDF (*.hpdf)",
        )
        if not path:
            return
        self._show_temporary_status("Abriendo proyecto…", 3000)
        QApplication.processEvents()
        try:
            project = load_project(path)
        except ProjectVersionError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        except ProjectAssetError as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"Falta un recurso interno necesario para abrir el proyecto.\n\n{exc}",
            )
            return
        except ProjectFormatError as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"El archivo de proyecto está dañado o no es válido.\n\n{exc}",
            )
            return
        except ProjectError as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"No se pudo abrir el proyecto.\n\n{exc}",
            )
            return

        self._replace_document(
            project.asset_manager,
            project.pages,
            project.page_order,
            project_path=project.source_project_path,
            project_id=project.project_id,
            created_at=project.created_at,
            modified_at=project.modified_at,
        )
        self._update_document_ui()
        self._show_temporary_status(
            f"Proyecto abierto: {project.source_project_path}",
            7000,
        )

    def save_project(self) -> bool:
        if not self.current_project_path:
            return self.save_project_as()
        return self._save_project_to(self.current_project_path)

    def save_project_as(self) -> bool:
        suggested = self.current_project_path or "Proyecto.hpdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar proyecto como",
            suggested,
            "Proyecto Habdorn PDF (*.hpdf)",
        )
        if not path:
            return False
        return self._save_project_to(path)

    def _save_project_to(self, path: str) -> bool:
        self.save_current_overlay_positions()
        modified_at = utc_now()
        project_name = Path(path).stem or "Proyecto"
        self._show_temporary_status("Guardando proyecto…", 3000)
        QApplication.processEvents()
        try:
            saved_path = save_project(
                path,
                self.pages,
                self.ordered_page_ids(),
                self.asset_manager,
                {
                    "id": self.project_id,
                    "name": project_name,
                    "created_at": self.project_created_at,
                    "modified_at": modified_at,
                },
            )
        except ProjectError as exc:
            QMessageBox.critical(
                self,
                APP_NAME,
                f"No se pudo guardar el proyecto.\n\n{exc}",
            )
            return False
        self.current_project_path = saved_path
        self.project_modified_at = modified_at
        self._mark_project_saved_state()
        self.update_window_title()
        self._show_temporary_status("Proyecto guardado", 5000)
        return True

    def _replace_document(
        self,
        asset_manager: AssetManager,
        pages: Dict[str, PageModel],
        page_order: List[str],
        *,
        project_path: Optional[str],
        project_id: str,
        created_at: str,
        modified_at: str,
    ) -> None:
        self._changing_selection = True
        self.page_list.blockSignals(True)
        try:
            self.page_list.clear()
            self.scene.clear()
            self.pages.clear()
            self.overlay_items.clear()
            self.thumbnail_cache.clear()
            self.current_page_id = None
            self.asset_manager = asset_manager
            self.current_project_path = project_path
            self.project_id = project_id
            self.project_created_at = created_at
            self.project_modified_at = modified_at
            for page_id in page_order:
                model = deepcopy(pages[page_id])
                self.pages[page_id] = model
                item = QListWidgetItem(model.label)
                item.setData(Qt.ItemDataRole.UserRole, model.id)
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                item.setToolTip(model.label)
                self.page_list.addItem(item)
                self._set_thumbnail(item, model)
        finally:
            self.page_list.blockSignals(False)
            self._changing_selection = False

        self.undo_stack.clear()
        self._direct_revision += 1
        if page_order:
            self.page_list.setCurrentRow(0)
            first_item = self.page_list.item(0)
            first_item.setSelected(True)
            self.load_page_into_preview(page_order[0])
        self._mark_project_saved_state()
        self.refresh_thumbnail_layout()
        self.update_window_title()
        self._update_document_ui()

    def _build_undo_shortcuts(self) -> None:
        self.redo_shift_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shift_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_shift_shortcut.activated.connect(self.undo_stack.redo)

    def _apply_style(self) -> None:
        colors = UI_COLORS
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: {colors['window']}; color: {colors['text']}; }}
            QWidget {{ color: {colors['text']}; }}
            QWidget#pagePanel, QWidget#workspacePanel {{
                background: {colors['panel']};
            }}
            QMenuBar {{
                background: {colors['window']};
                color: {colors['text']};
                padding: 5px 8px;
                spacing: 4px;
            }}
            QMenuBar::item {{ padding: 7px 11px; border-radius: 5px; }}
            QMenuBar::item:selected, QMenu::item:selected {{
                background: {colors['surface_hover']};
            }}
            QMenu {{
                background: {colors['panel']};
                border: 1px solid {colors['border']};
                padding: 6px;
            }}
            QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 4px; }}
            QToolBar#mainToolbar {{
                background: {colors['window']};
                border: 0;
                border-top: 1px solid {colors['border']};
                border-bottom: 1px solid {colors['border']};
                spacing: 4px;
                padding: 7px 10px;
            }}
            QToolBar::separator {{
                background: {colors['border']};
                width: 1px;
                margin: 7px 6px;
            }}
            QToolButton {{
                background: {colors['surface']};
                color: {colors['text']};
                font-size: 11px;
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 5px 7px;
            }}
            QToolButton:hover {{
                background: {colors['surface_hover']};
                border-color: {colors['accent']};
            }}
            QToolButton:pressed {{ background: {colors['accent']}; }}
            QToolButton:focus {{ border: 1px solid {colors['accent_hover']}; }}
            QToolButton:disabled {{
                background: #23272e;
                color: #69717d;
                border-color: #303640;
            }}
            QToolButton[role="primary"] {{
                background: {colors['accent']};
                border-color: {colors['accent_hover']};
                font-weight: 700;
            }}
            QToolButton[role="primary"]:hover {{ background: {colors['accent_hover']}; }}
            QToolButton[role="secondary"] {{
                background: #303844;
                border-color: #596678;
                font-weight: 600;
            }}
            QToolButton[role="destructive"]:hover {{
                background: #43332f;
                border-color: {colors['warning']};
            }}
            QStackedWidget#pageListStack, QStackedWidget#previewStack {{
                background: transparent;
                border: 0;
            }}
            QListWidget {{
                background: {colors['window']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QListWidget::item {{
                color: #e8ebef;
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 5px;
            }}
            QListWidget::item:selected {{
                background: #293c56;
                border: 1px solid {colors['accent']};
            }}
            QListWidget::item:hover {{ background: #252b33; }}
            QWidget#emptyPages, QWidget#welcomePage {{
                background: {colors['window']};
                border: 1px solid {colors['border']};
                border-radius: 9px;
            }}
            QFrame#previewFrame {{
                background: #15181d;
                border: 1px solid {colors['border']};
                border-radius: 9px;
            }}
            QGraphicsView {{
                background: #15181d;
                border: 0;
                border-radius: 6px;
            }}
            QLabel#sectionTitle {{
                font-size: 13px;
                font-weight: 700;
                color: #a9c9ef;
                letter-spacing: 1px;
            }}
            QLabel#pageCount, QLabel#helpText,
            QLabel#emptyPagesText, QLabel#welcomeText {{
                color: {colors['muted']};
            }}
            QLabel#pageCount {{ font-size: 12px; }}
            QLabel#helpText {{ font-size: 12px; padding: 0 4px 3px 4px; }}
            QLabel#emptyPagesTitle {{ font-size: 14px; font-weight: 600; }}
            QLabel#welcomeTitle {{ font-size: 26px; font-weight: 700; }}
            QLabel#welcomeText {{ font-size: 14px; }}
            QPushButton[role="welcome"] {{
                background: {colors['surface']};
                border: 1px solid {colors['border']};
                border-radius: 7px;
                padding: 8px 14px;
            }}
            QPushButton[role="welcome"]:hover {{
                background: {colors['surface_hover']};
                border-color: {colors['accent']};
            }}
            QPushButton[role="welcome"]:focus {{ border-color: {colors['accent_hover']}; }}
            QPushButton[role="link"] {{
                background: transparent;
                border: 0;
                color: #85b8f0;
                padding: 6px 10px;
                text-decoration: underline;
            }}
            QPushButton[role="link"]:hover {{ color: #b0d2f5; }}
            QSplitter::handle {{ background: {colors['border']}; }}
            QStatusBar {{
                background: {colors['window']};
                color: {colors['muted']};
                border-top: 1px solid {colors['border']};
                padding: 3px 10px;
            }}
            """
        )

    def ordered_page_ids(self) -> List[str]:
        return [self.page_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.page_list.count())]

    @staticmethod
    def _is_valid_page_order(order: List[str], expected: List[str]) -> bool:
        return len(order) == len(expected) and len(set(order)) == len(order) and set(order) == set(expected)

    def on_native_drop_finished(self, old_order: List[str], new_order: List[str]) -> None:
        current_order = self.ordered_page_ids()
        if old_order == new_order:
            self.refresh_thumbnail_layout()
            return
        if not self._is_valid_page_order(old_order, current_order):
            self.refresh_thumbnail_layout()
            return
        if not self._is_valid_page_order(new_order, current_order):
            self.refresh_thumbnail_layout()
            return
        self.undo_stack.push(ReorderPagesCommand(self, old_order, new_order, skip_first_redo=True))
        self.refresh_thumbnail_layout()
        self._update_document_ui()

    def _apply_page_order(self, order: List[str]) -> None:
        current_order = self.ordered_page_ids()
        if not self._is_valid_page_order(order, current_order):
            return

        selected_ids = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.page_list.selectedItems()
        }
        current_id = self.current_page_id if self.current_page_id in self.pages else None

        was_blocked = self.page_list.blockSignals(True)
        self._changing_selection = True
        try:
            items_by_id = {}
            while self.page_list.count():
                item = self.page_list.takeItem(0)
                items_by_id[item.data(Qt.ItemDataRole.UserRole)] = item

            for page_id in order:
                self.page_list.addItem(items_by_id[page_id])
            self.page_list.clearSelection()
            target_current_id = current_id if current_id in order else (order[0] if order else None)
            for index in range(self.page_list.count()):
                item = self.page_list.item(index)
                page_id = item.data(Qt.ItemDataRole.UserRole)
                item.setSelected(page_id in selected_ids)
                if page_id == target_current_id:
                    self.page_list.setCurrentRow(index)
        finally:
            self._changing_selection = False
            self.page_list.blockSignals(was_blocked)

        if current_id and current_id in order:
            self.load_page_into_preview(current_id)
        elif order:
            self.load_page_into_preview(order[0])
        else:
            self.current_page_id = None
            self.scene.clear()
            self.overlay_items.clear()
        self.refresh_thumbnail_layout()
        self._update_document_ui()

    def _insert_page_models(self, models: List[PageModel], command_text: str = "Agregar página") -> None:
        if not models:
            return
        current_row = self.page_list.currentRow()
        insert_at = current_row + 1 if current_row >= 0 else self.page_list.count()
        self.undo_stack.push(InsertPagesCommand(self, models, insert_at, command_text))

    def _insert_page_models_direct(self, models: List[PageModel], insert_at: int) -> None:
        if not models:
            return
        insert_at = min(max(insert_at, 0), self.page_list.count())
        for offset, model in enumerate(models):
            stored_model = deepcopy(model)
            self.pages[stored_model.id] = stored_model
            item = QListWidgetItem(stored_model.label)
            item.setData(Qt.ItemDataRole.UserRole, stored_model.id)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setToolTip(stored_model.label)
            self.page_list.insertItem(insert_at + offset, item)
            self._set_thumbnail(item, stored_model)
        self.page_list.clearSelection()
        self.page_list.setCurrentRow(insert_at)
        current = self.page_list.item(insert_at)
        if current:
            current.setSelected(True)
        self.refresh_thumbnail_layout()
        self._update_document_ui()
        self._show_temporary_status(
            f"{len(models)} página(s) añadida(s)",
            4000,
        )

    def _remove_page_ids_direct(self, page_ids: List[str], select_row: Optional[int] = None) -> None:
        ids = set(page_ids)
        removed_rows = []
        self.save_current_overlay_positions()
        for row in range(self.page_list.count() - 1, -1, -1):
            item = self.page_list.item(row)
            page_id = item.data(Qt.ItemDataRole.UserRole)
            if page_id not in ids:
                continue
            removed_rows.append(row)
            self.page_list.takeItem(row)
            self.pages.pop(page_id, None)
            self.thumbnail_cache.pop(page_id, None)
        if self.current_page_id in ids:
            self.current_page_id = None
            self.scene.clear()
            self.overlay_items.clear()
        if self.page_list.count():
            target = select_row
            if target is None:
                target = min(min(removed_rows) if removed_rows else 0, self.page_list.count() - 1)
            self.page_list.setCurrentRow(min(max(target, 0), self.page_list.count() - 1))
        self.refresh_thumbnail_layout()
        self._update_document_ui()

    def add_pdfs(self) -> None:
        document_was_empty = len(self.pages) == 0 and self.page_list.count() == 0
        paths, _ = QFileDialog.getOpenFileNames(self, "Seleccionar PDF", "", "Archivos PDF (*.pdf)")
        models: List[PageModel] = []
        for path in paths:
            try:
                with fitz.open(path) as source_doc:
                    if source_doc.needs_pass:
                        QMessageBox.warning(
                            self,
                            APP_NAME,
                            f"El PDF está protegido con contraseña:\n{path}",
                        )
                        continue

                asset = self.asset_manager.import_asset(path, "pdf")
                internal_path = self.asset_manager.resolve_path(asset.id)
                with fitz.open(internal_path) as doc:
                    for index in range(doc.page_count):
                        page = doc.load_page(index)
                        models.append(
                            PageModel(
                                id=uuid.uuid4().hex,
                                kind="pdf",
                                source=internal_path,
                                page_index=index,
                                width_pt=page.rect.width,
                                height_pt=page.rect.height,
                                label=(
                                    f"{asset.original_name}\n"
                                    f"Pág. {index + 1}"
                                ),
                                asset_id=asset.id,
                            )
                        )
            except Exception as exc:
                QMessageBox.critical(self, APP_NAME, f"No se pudo abrir:\n{path}\n\n{exc}")
        if models:
            if document_was_empty:
                current_row = self.page_list.currentRow()
                insert_at = current_row + 1 if current_row >= 0 else self.page_list.count()
                self._insert_page_models_direct(models, insert_at)
                self.undo_stack.clear()
                self._mark_direct_change()
                return
            self._insert_page_models(models, "Agregar PDF")

    def add_images_as_pages(self) -> None:
        was_empty = not self.pages and self.page_list.count() == 0
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar imágenes",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        )
        models: List[PageModel] = []
        for path in paths:
            try:
                with Image.open(path) as img:
                    img.verify()
                asset = self.asset_manager.import_asset(path, "image")
                internal_path = self.asset_manager.resolve_path(asset.id)
                with Image.open(internal_path) as img:
                    width, height = img.size
                if width >= height:
                    page_w, page_h = A4_PORTRAIT[1], A4_PORTRAIT[0]
                else:
                    page_w, page_h = A4_PORTRAIT
                models.append(
                    PageModel(
                        id=uuid.uuid4().hex,
                        kind="image",
                        source=internal_path,
                        width_pt=page_w,
                        height_pt=page_h,
                        label=f"Imagen\n{asset.original_name}",
                        asset_id=asset.id,
                    )
                )
            except Exception as exc:
                QMessageBox.warning(self, APP_NAME, f"No se pudo leer la imagen:\n{path}\n\n{exc}")
        if not models:
            return
        if was_empty:
            self._insert_page_models_direct(models, self.page_list.count())
            self.undo_stack.clear()
            self._mark_direct_change()
            return
        self._insert_page_models(models, "Agregar imagen como página")

    def add_blank_page(self) -> None:
        model = PageModel(
            id=uuid.uuid4().hex,
            kind="blank",
            width_pt=A4_PORTRAIT[0],
            height_pt=A4_PORTRAIT[1],
            label="Página en blanco\nA4",
        )
        self._insert_page_models([model], "Agregar página en blanco")

    def add_overlay_image(self) -> None:
        if not self.current_page_id:
            QMessageBox.information(self, APP_NAME, "Selecciona una página primero.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Insertar imagen en la página",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, APP_NAME, "No se pudo abrir esa imagen.")
            return

        try:
            asset = self.asset_manager.import_asset(path, "image")
            internal_path = self.asset_manager.resolve_path(asset.id)
            pixmap = QPixmap(internal_path)
            if pixmap.isNull():
                raise AssetManagerError(
                    "No se pudo validar la copia interna de la imagen."
                )
        except Exception as exc:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"No se pudo crear la copia interna de la imagen.\n\n{exc}",
            )
            return

        self.save_current_overlay_positions()
        page = self.pages[self.current_page_id]
        ratio = pixmap.width() / max(1, pixmap.height())
        page_w, page_h = self._rotated_page_size(page.width_pt, page.height_pt, page.rotation)
        norm_w = 0.42
        norm_h = norm_w * (page_w / page_h) / ratio
        if norm_h > 0.55:
            norm_h = 0.55
            norm_w = norm_h * ratio * (page_h / page_w)
        overlay = OverlayModel(
            id=uuid.uuid4().hex,
            path=internal_path,
            x=(1 - norm_w) / 2,
            y=(1 - norm_h) / 2,
            w=norm_w,
            h=norm_h,
            asset_id=asset.id,
        )
        self.undo_stack.push(InsertOverlayCommand(self, page.id, overlay))
        self._show_temporary_status(
            "Imagen insertada: arrástrala y redimensiónala",
            4500,
        )

    def delete_selected_overlays(self) -> None:
        if not self.current_page_id:
            return
        selected_ids = [
            item.model_id
            for item in self.scene.selectedItems()
            if isinstance(item, OverlayGraphicsItem)
        ]
        if not selected_ids:
            return
        self.save_current_overlay_positions()
        page = self.pages[self.current_page_id]
        overlays = [
            (index, deepcopy(overlay))
            for index, overlay in enumerate(page.overlays)
            if overlay.id in selected_ids
        ]
        self.undo_stack.push(DeleteOverlaysCommand(self, page.id, overlays))

    def delete_selected_pages(self) -> None:
        selected = self.page_list.selectedItems()
        if not selected:
            return
        self.save_current_overlay_positions()
        rows_and_models = []
        for item in selected:
            row = self.page_list.row(item)
            page_id = item.data(Qt.ItemDataRole.UserRole)
            page = self.pages.get(page_id)
            if page:
                rows_and_models.append((row, deepcopy(page)))
        self.undo_stack.push(DeletePagesCommand(self, rows_and_models))

    def rotate_selected_pages(self, delta: int) -> None:
        selected = self.page_list.selectedItems()
        if not selected:
            return
        self.save_current_overlay_positions()
        selected_ids = [item.data(Qt.ItemDataRole.UserRole) for item in selected]
        self.undo_stack.push(RotatePagesCommand(self, selected_ids, delta))

    def _rotate_pages_direct(self, page_ids: List[str], delta: int) -> None:
        selected_ids = [page_id for page_id in page_ids if page_id in self.pages]
        for page_id in selected_ids:
            page = self.pages.get(page_id)
            if not page:
                continue
            for overlay in page.overlays:
                self._rotate_overlay(overlay, delta)
            page.rotation = (page.rotation + delta) % 360

        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            page_id = item.data(Qt.ItemDataRole.UserRole)
            if page_id in selected_ids and page_id in self.pages:
                self._set_thumbnail(item, self.pages[page_id])

        if self.current_page_id in selected_ids:
            self.load_page_into_preview(self.current_page_id)

        direction = "izquierda" if delta < 0 else "derecha"
        self.refresh_thumbnail_layout()
        self._show_temporary_status(
            f"{len(selected_ids)} página(s) rotada(s) a la {direction}",
            4000,
        )

    def on_page_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if self._changing_selection:
            return
        self.save_current_overlay_positions()
        if current is None:
            self.current_page_id = None
            self.scene.clear()
            self._update_document_ui()
            return
        page_id = current.data(Qt.ItemDataRole.UserRole)
        self.load_page_into_preview(page_id)
        self._update_document_ui()

    def save_current_overlay_positions(self) -> None:
        if not self.current_page_id or self.current_page_id not in self.pages:
            return
        page = self.pages[self.current_page_id]
        if not self.overlay_items:
            return
        scene_rect = self.scene.sceneRect()
        pw = max(1.0, scene_rect.width())
        ph = max(1.0, scene_rect.height())
        by_id = {o.id: o for o in page.overlays}
        for overlay_id, item in self.overlay_items.items():
            model = by_id.get(overlay_id)
            if not model:
                continue
            r = item.rect()
            p = item.pos()
            model.x = min(max((p.x() + r.left()) / pw, 0.0), 1.0)
            model.y = min(max((p.y() + r.top()) / ph, 0.0), 1.0)
            model.w = min(max(r.width() / pw, 0.001), 1.0)
            model.h = min(max(r.height() / ph, 0.001), 1.0)
            model.rotation = item.overlay_rotation()
        self._refresh_current_thumbnail()

    def _insert_overlay_direct(self, page_id: str, overlay: OverlayModel) -> None:
        page = self.pages.get(page_id)
        if not page:
            return
        self._insert_overlays_direct(page_id, [(len(page.overlays), overlay)])

    def _insert_overlays_direct(self, page_id: str, overlays: List[Tuple[int, OverlayModel]]) -> None:
        page = self.pages.get(page_id)
        if not page:
            return
        for index, overlay in sorted(overlays, key=lambda item: item[0]):
            page.overlays.insert(min(max(index, 0), len(page.overlays)), deepcopy(overlay))
        if self.current_page_id == page_id:
            self.load_page_into_preview(page_id)
        self._refresh_page_thumbnail(page_id)

    def _remove_overlay_ids_direct(self, page_id: str, overlay_ids: List[str]) -> None:
        page = self.pages.get(page_id)
        if not page:
            return
        ids = set(overlay_ids)
        page.overlays = [overlay for overlay in page.overlays if overlay.id not in ids]
        if self.current_page_id == page_id:
            self.load_page_into_preview(page_id)
        self._refresh_page_thumbnail(page_id)

    def _replace_overlay_direct(self, page_id: str, overlay: OverlayModel) -> None:
        page = self.pages.get(page_id)
        if not page:
            return
        for index, current in enumerate(page.overlays):
            if current.id == overlay.id:
                page.overlays[index] = deepcopy(overlay)
                break
        if self.current_page_id == page_id:
            self.load_page_into_preview(page_id)
        self._refresh_page_thumbnail(page_id)

    def _overlay_from_item_state(
        self,
        page_id: str,
        overlay_id: str,
        state: Tuple[float, float, float, float, float, float, float],
    ) -> Optional[OverlayModel]:
        page = self.pages.get(page_id)
        if not page:
            return None
        source = next((overlay for overlay in page.overlays if overlay.id == overlay_id), None)
        if not source:
            return None
        scene_rect = self.scene.sceneRect()
        pw = max(1.0, scene_rect.width())
        ph = max(1.0, scene_rect.height())
        pos_x, pos_y, rect_x, rect_y, rect_w, rect_h, rotation = state
        overlay = deepcopy(source)
        overlay.x = min(max((pos_x + rect_x) / pw, 0.0), 1.0)
        overlay.y = min(max((pos_y + rect_y) / ph, 0.0), 1.0)
        overlay.w = min(max(rect_w / pw, 0.001), 1.0)
        overlay.h = min(max(rect_h / ph, 0.001), 1.0)
        overlay.rotation = rotation
        return overlay

    def _overlay_geometry_committed(
        self,
        overlay_id: str,
        before_state: Tuple[float, float, float, float, float, float, float],
        after_state: Tuple[float, float, float, float, float, float, float],
    ) -> None:
        if not self.current_page_id:
            return
        before = self._overlay_from_item_state(self.current_page_id, overlay_id, before_state)
        after = self._overlay_from_item_state(self.current_page_id, overlay_id, after_state)
        if not before or not after:
            return
        if before.rotation != after.rotation:
            text = "Rotar imagen"
        elif before.w != after.w or before.h != after.h:
            text = "Redimensionar imagen"
        else:
            text = "Mover imagen"
        self.undo_stack.push(UpdateOverlayCommand(self, self.current_page_id, before, after, text))

    def load_page_into_preview(self, page_id: str) -> None:
        page = self.pages.get(page_id)
        if not page:
            return
        self.current_page_id = page_id
        self.scene.clear()
        self.overlay_items.clear()

        base = self.render_page_pixmap(page, target_long_edge=1500, include_overlays=False)
        if base.isNull():
            return
        self.scene.setSceneRect(QRectF(0, 0, base.width(), base.height()))
        base_item = self.scene.addPixmap(base)
        base_item.setZValue(0)

        page_rect = self.scene.sceneRect()
        rotation = page.rotation % 360
        for overlay in page.overlays:
            try:
                overlay_path = (
                    self.asset_manager.resolve_path(overlay.asset_id)
                    if overlay.asset_id
                    else overlay.path
                )
            except AssetManagerError as exc:
                self._show_temporary_status(str(exc), 7000)
                continue
            pixmap = QPixmap(overlay_path)
            if pixmap.isNull():
                continue
            if rotation:
                pixmap = pixmap.transformed(
                    QTransform().rotate(rotation),
                    Qt.TransformationMode.SmoothTransformation,
                )
            rect = QRectF(0, 0, overlay.w * page_rect.width(), overlay.h * page_rect.height())
            item = OverlayGraphicsItem(overlay.id, pixmap, rect, page_rect, overlay.rotation)
            item.geometry_committed = self._overlay_geometry_committed
            item.setPos(overlay.x * page_rect.width(), overlay.y * page_rect.height())
            self.scene.addItem(item)
            self.overlay_items[overlay.id] = item

        self.preview.resetTransform()
        self.preview.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.update_status_bar()

    def render_page_pixmap(self, page: PageModel, target_long_edge: int = 900, include_overlays: bool = True) -> QPixmap:
        try:
            return render_page_pixmap_service(
                page,
                target_long_edge,
                include_overlays,
                self.asset_manager.resolve_path,
            )
        except AssetManagerError as exc:
            self._show_temporary_status(str(exc), 7000)
            placeholder = QPixmap(480, 640)
            placeholder.fill(QColor("#ffffff"))
            return placeholder

    def _set_thumbnail(self, item: QListWidgetItem, page: PageModel) -> None:
        pixmap = self.render_page_pixmap(page, target_long_edge=430, include_overlays=True)
        max_w = 176
        max_h = 205
        fitted = pixmap.scaled(
            max_w - 8,
            max_h - 8,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        thumb = QPixmap(fitted.width() + 8, fitted.height() + 8)
        thumb.fill(QColor("#111318"))
        painter = QPainter(thumb)
        painter.setPen(QPen(QColor("#4b515d"), 1))
        x = (thumb.width() - fitted.width()) // 2
        y = (thumb.height() - fitted.height()) // 2
        painter.fillRect(x, y, fitted.width(), fitted.height(), QColor("white"))
        painter.drawPixmap(x, y, fitted)
        painter.drawRect(x, y, fitted.width() - 1, fitted.height() - 1)
        painter.end()
        self.thumbnail_cache[page.id] = thumb
        item.setIcon(QIcon(thumb))
        item.setSizeHint(QSize(246, thumb.height() + 42))

    def _refresh_current_thumbnail(self) -> None:
        if not self.current_page_id:
            return
        self._refresh_page_thumbnail(self.current_page_id)

    def _refresh_page_thumbnail(self, page_id: str) -> None:
        if page_id not in self.pages:
            return
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                self._set_thumbnail(item, self.pages[page_id])
                break
        self.refresh_thumbnail_layout()

    def refresh_thumbnail_layout(self) -> None:
        QTimer.singleShot(0, self._refresh_thumbnail_layout_now)

    def _refresh_thumbnail_layout_now(self) -> None:
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            page_id = item.data(Qt.ItemDataRole.UserRole)
            page = self.pages.get(page_id)
            if page:
                self._set_thumbnail(item, page)
        self.page_list.scheduleDelayedItemsLayout()
        self.page_list.doItemsLayout()
        self.page_list.updateGeometries()
        self.page_list.viewport().update()

    @staticmethod
    def _rotate_overlay(overlay: OverlayModel, delta: int) -> None:
        rotate_overlay(overlay, delta)

    @staticmethod
    def _rotated_page_size(width: float, height: float, rotation: int) -> Tuple[float, float]:
        return rotated_page_size(width, height, rotation)

    @staticmethod
    def _rotate_rect(rect: fitz.Rect, width: float, height: float, rotation: int) -> fitz.Rect:
        return rotate_rect(rect, width, height, rotation)

    @staticmethod
    def _rotated_image_stream(path: str, rotation: float) -> bytes:
        return rotated_image_stream(path, rotation)

    @staticmethod
    def _fit_rect(page_w: float, page_h: float, image_w: int, image_h: int, margin: float = 20.0) -> fitz.Rect:
        return fit_rect(page_w, page_h, image_w, image_h, margin)

    def _update_export_progress(
        self,
        progress: QProgressDialog,
        value: int,
        total: int,
    ) -> None:
        self._has_temporary_status = True
        progress.setValue(value)
        self.statusBar().showMessage(
            f"Exportando página {value} de {total}…"
        )
        QApplication.processEvents()

    def export_pdf(self) -> None:
        if self.page_list.count() == 0:
            QMessageBox.information(self, APP_NAME, "Todavía no hay páginas para exportar.")
            return
        self.save_current_overlay_positions()
        path, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", "documento_final.pdf", "Archivo PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        progress = QProgressDialog("Creando PDF...", "Cancelar", 0, self.page_list.count(), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        total_pages = self.page_list.count()
        self._status_generation += 1

        try:
            completed = export_pdf_document(
                self.pages,
                self.ordered_page_ids(),
                path,
                lambda value: self._update_export_progress(
                    progress,
                    value,
                    total_pages,
                ),
                progress.wasCanceled,
                self.asset_manager.resolve_path,
            )
            progress.close()
            if not completed:
                self._has_temporary_status = False
                self.update_status_bar(force=True)
                return
            self._show_temporary_status(f"PDF exportado: {path}", 7000)
            QMessageBox.information(
                self,
                APP_NAME,
                f"PDF creado correctamente:\n{path}",
            )
        except Exception as exc:
            progress.close()
            self._has_temporary_status = False
            self.update_status_bar(force=True)
            QMessageBox.critical(
                self,
                APP_NAME,
                f"No se pudo exportar el PDF.\n\n{exc}",
            )

    def _confirm_discard_changes(self) -> bool:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Cambios sin guardar")
        message_box.setText(
            "El proyecto contiene cambios que todavía no han sido "
            "guardados.\n\n"
            "¿Deseas continuar y perder esos cambios?"
        )
        close_button = message_box.addButton(
            "Descartar cambios",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = message_box.addButton(
            "Cancelar",
            QMessageBox.ButtonRole.RejectRole,
        )
        message_box.setDefaultButton(cancel_button)
        message_box.exec()
        return message_box.clickedButton() is close_button

    def closeEvent(self, event) -> None:
        if self.is_dirty and not self._confirm_discard_changes():
            event.ignore()
            return
        self.save_current_overlay_positions()
        event.accept()
