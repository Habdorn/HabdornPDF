from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
from app.constants import A4_PORTRAIT, APP_NAME
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
    QGraphicsScene,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QToolBar,
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
        self.current_page_id: Optional[str] = None
        self.overlay_items: Dict[str, OverlayGraphicsItem] = {}
        self.thumbnail_cache: Dict[str, QPixmap] = {}
        self._changing_selection = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(20)
        self._direct_revision = 0
        self._saved_direct_revision = 0
        self._saved_undo_index = self.undo_stack.index()
        self.is_dirty = False
        self.undo_stack.indexChanged.connect(self._update_dirty_state)
        self.undo_stack.cleanChanged.connect(self._update_dirty_state)
        self.undo_stack.setClean()

        self.scene = QGraphicsScene(self)
        self.preview = PreviewView(self.scene)
        self.preview.delete_pressed.connect(self.delete_selected_overlays)

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
        self.page_list.native_drop_finished.connect(self.on_native_drop_finished)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 8, 10)
        title = QLabel("PÁGINAS")
        title.setObjectName("sectionTitle")
        left_layout.addWidget(title)
        left_layout.addWidget(self.page_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 10, 10, 10)
        help_label = QLabel(
            "Arrastra las miniaturas para reordenar. En la página, mueve la imagen y usa el cuadro azul para cambiar su tamaño. Ctrl + rueda: zoom."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("helpText")
        right_layout.addWidget(help_label)
        right_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([340, 1050])
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menu()
        self._build_undo_shortcuts()
        self._apply_style()
        self.statusBar().showMessage("Añade PDF o imágenes para comenzar")
        self.update_window_title()

    def set_dirty(self, dirty: bool = True) -> None:
        if self.is_dirty == dirty:
            return
        self.is_dirty = dirty
        self.update_window_title()

    def update_window_title(self) -> None:
        suffix = " *" if self.is_dirty else ""
        self.setWindowTitle(f"{APP_NAME}{suffix}")

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

    def _mark_exported_state(self) -> None:
        self._saved_undo_index = self.undo_stack.index()
        self._saved_direct_revision = self._direct_revision
        self.undo_stack.setClean()
        self._update_dirty_state()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Herramientas")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        self.undo_action = self.undo_stack.createUndoAction(self, "Deshacer")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_action = self.undo_stack.createRedoAction(self, "Rehacer")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.toolbar_undo_action = QAction("Deshacer", self)
        self.toolbar_undo_action.triggered.connect(self.undo_action.trigger)
        self.toolbar_redo_action = QAction("Rehacer", self)
        self.toolbar_redo_action.triggered.connect(self.redo_action.trigger)
        self.undo_action.changed.connect(self._sync_toolbar_undo_redo_actions)
        self.redo_action.changed.connect(self._sync_toolbar_undo_redo_actions)
        self._sync_toolbar_undo_redo_actions()
        toolbar.addAction(self.toolbar_undo_action)
        toolbar.addAction(self.toolbar_redo_action)
        toolbar.addSeparator()

        actions = [
            ("+ PDF", self.add_pdfs),
            ("+ Imagen como página", self.add_images_as_pages),
            ("+ Página en blanco", self.add_blank_page),
            ("Insertar imagen", self.add_overlay_image),
            ("Rotar izquierda", lambda: self.rotate_selected_pages(-90)),
            ("Rotar derecha", lambda: self.rotate_selected_pages(90)),
            ("Eliminar imagen", self.delete_selected_overlays),
            ("Eliminar página", self.delete_selected_pages),
            ("Exportar PDF", self.export_pdf),
        ]
        for text, callback in actions:
            action = QAction(text, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
            if text in {"+ Página en blanco", "Eliminar página"}:
                toolbar.addSeparator()

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
        add_pdf = QAction("Añadir PDF", self)
        add_pdf.setShortcut(QKeySequence.StandardKey.Open)
        add_pdf.triggered.connect(self.add_pdfs)
        file_menu.addAction(add_pdf)

        export = QAction("Exportar PDF", self)
        export.setShortcut(QKeySequence.StandardKey.SaveAs)
        export.triggered.connect(self.export_pdf)
        file_menu.addAction(export)

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
        rotate_left = QAction("Rotar izquierda", self)
        rotate_left.setShortcut(QKeySequence("Ctrl+Shift+L"))
        rotate_left.triggered.connect(lambda: self.rotate_selected_pages(-90))
        page_menu.addAction(rotate_left)

        rotate_right = QAction("Rotar derecha", self)
        rotate_right.setShortcut(QKeySequence("Ctrl+Shift+R"))
        rotate_right.triggered.connect(lambda: self.rotate_selected_pages(90))
        page_menu.addAction(rotate_right)

    def _build_undo_shortcuts(self) -> None:
        self.redo_shift_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shift_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_shift_shortcut.activated.connect(self.undo_stack.redo)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #202329; color: #edf0f5; }
            QMenuBar { background: #17191d; color: #edf0f5; }
            QMenuBar::item:selected, QMenu::item:selected { background: #2f80ed; }
            QMenu { background: #202329; border: 1px solid #343942; }
            QToolBar { background: #17191d; border: 0; spacing: 5px; padding: 6px; }
            QToolButton { background: #2a2e35; color: #f5f7fa; border: 1px solid #3a404a; border-radius: 6px; padding: 8px 12px; }
            QToolButton:hover { background: #343a44; border-color: #5aa9ff; }
            QToolButton:pressed { background: #2f80ed; }
            QListWidget { background: #17191d; border: 1px solid #343942; border-radius: 8px; padding: 8px; }
            QListWidget::item { color: #e8ebef; border: 1px solid transparent; border-radius: 7px; padding: 5px; }
            QListWidget::item:selected { background: #28374d; border: 1px solid #5aa9ff; }
            QListWidget::item:hover { background: #242932; }
            QGraphicsView { border: 1px solid #343942; border-radius: 8px; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 700; color: #8fc3ff; letter-spacing: 1px; }
            QLabel#helpText { color: #aeb6c2; padding: 2px 4px 6px 4px; }
            QStatusBar { background: #17191d; color: #b7bec8; }
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
        self.statusBar().showMessage(f"{len(models)} página(s) añadida(s)", 4000)

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
        else:
            self.statusBar().showMessage("Añade PDF o imágenes para comenzar")
        self.refresh_thumbnail_layout()

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
        self.statusBar().showMessage("Imagen insertada: arrástrala y redimensiónala", 4500)

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
        self.statusBar().showMessage(f"{len(selected_ids)} página(s) rotada(s) a la {direction}", 4000)

    def on_page_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if self._changing_selection:
            return
        self.save_current_overlay_positions()
        if current is None:
            self.current_page_id = None
            self.scene.clear()
            return
        page_id = current.data(Qt.ItemDataRole.UserRole)
        self.load_page_into_preview(page_id)

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
                self.statusBar().showMessage(str(exc), 7000)
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
        self.statusBar().showMessage(page.label.replace("\n", " - "))

    def render_page_pixmap(self, page: PageModel, target_long_edge: int = 900, include_overlays: bool = True) -> QPixmap:
        try:
            return render_page_pixmap_service(
                page,
                target_long_edge,
                include_overlays,
                self.asset_manager.resolve_path,
            )
        except AssetManagerError as exc:
            self.statusBar().showMessage(str(exc), 7000)
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

        try:
            completed = export_pdf_document(
                self.pages,
                self.ordered_page_ids(),
                path,
                lambda value: (
                    progress.setValue(value),
                    QApplication.processEvents(),
                ),
                progress.wasCanceled,
                self.asset_manager.resolve_path,
            )
            progress.close()
            if not completed:
                return
            self._mark_exported_state()
            self.statusBar().showMessage(f"PDF exportado: {path}", 7000)
            QMessageBox.information(
                self,
                APP_NAME,
                f"PDF creado correctamente:\n{path}",
            )
        except Exception as exc:
            progress.close()
            QMessageBox.critical(
                self,
                APP_NAME,
                f"No se pudo exportar el PDF.\n\n{exc}",
            )

    def _confirm_discard_changes(self) -> bool:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Cambios sin exportar")
        message_box.setText(
            "El documento contiene cambios que todavía no han sido "
            "exportados.\n\n"
            "¿Deseas cerrar la aplicación y perder esos cambios?"
        )
        close_button = message_box.addButton(
            "Cerrar sin exportar",
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
