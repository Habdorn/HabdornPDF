from __future__ import annotations

import os
import sys
import uuid
import math
from copy import deepcopy
from io import BytesIO
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QBrush,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QTransform,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Habdorn PDF"
A4_PORTRAIT = (595.276, 841.89)
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class OverlayModel:
    id: str
    path: str
    x: float
    y: float
    w: float
    h: float
    rotation: float = 0.0


@dataclass
class PageModel:
    id: str
    kind: str  # pdf | image | blank
    source: Optional[str] = None
    page_index: Optional[int] = None
    width_pt: float = A4_PORTRAIT[0]
    height_pt: float = A4_PORTRAIT[1]
    rotation: int = 0
    label: str = "Página"
    overlays: List[OverlayModel] = field(default_factory=list)


class OverlayGraphicsItem(QGraphicsItem):
    HANDLE = 16.0
    ROTATE_OFFSET = 32.0

    def __init__(self, model_id: str, pixmap: QPixmap, rect: QRectF, page_rect: QRectF, rotation: float = 0.0):
        super().__init__()
        self.model_id = model_id
        self.pixmap = pixmap
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self.page_rect = QRectF(page_rect)
        self._resizing = False
        self._resize_handle: Optional[str] = None
        self._resize_anchor_scene = QPointF()
        self._rotating = False
        self._rotate_start_angle = 0.0
        self._rotate_start_rotation = rotation
        self._aspect = pixmap.width() / max(1, pixmap.height())
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(10)
        self.setTransformOriginPoint(self._rect.center())
        self.setRotation(rotation)
        self.geometry_committed = None
        self._undo_geometry_state = None

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def overlay_rotation(self) -> float:
        return self.rotation() % 360

    def boundingRect(self) -> QRectF:
        pad = self.HANDLE + self.ROTATE_OFFSET + 6.0
        return self._rect.adjusted(-pad, -pad, pad, pad)

    def handle_rect(self, handle: str) -> QRectF:
        half = self.HANDLE / 2.0
        points = {
            "tl": self._rect.topLeft(),
            "tr": self._rect.topRight(),
            "bl": self._rect.bottomLeft(),
            "br": self._rect.bottomRight(),
        }
        p = points[handle]
        return QRectF(
            p.x() - half,
            p.y() - half,
            self.HANDLE,
            self.HANDLE,
        )

    def rotate_handle_rect(self) -> QRectF:
        half = self.HANDLE / 2.0
        center = QPointF(self._rect.center().x(), self._rect.top() - self.ROTATE_OFFSET)
        return QRectF(center.x() - half, center.y() - half, self.HANDLE, self.HANDLE)

    def handle_at(self, pos: QPointF) -> Optional[str]:
        if self.rotate_handle_rect().contains(pos):
            return "rotate"
        for handle in ("tl", "tr", "bl", "br"):
            if self.handle_rect(handle).contains(pos):
                return handle
        return None

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(self._rect, self.pixmap, self.pixmap.rect())
        if self.isSelected():
            painter.setPen(QPen(QColor("#5aa9ff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(QBrush(QColor("#2f80ed")))
            for handle in ("tl", "tr", "bl", "br"):
                painter.drawRect(self.handle_rect(handle))
            painter.setPen(QPen(QColor("#8fc3ff"), 1))
            painter.drawLine(self._rect.center(), self.rotate_handle_rect().center())
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(QBrush(QColor("#43c6ac")))
            painter.drawEllipse(self.rotate_handle_rect())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._undo_geometry_state = self._geometry_state()
        handle = self.handle_at(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and handle == "rotate":
            self._rotating = True
            center = self._rect.center()
            vector = event.pos() - center
            self._rotate_start_angle = math.degrees(math.atan2(vector.y(), vector.x()))
            self._rotate_start_rotation = self.rotation()
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and handle:
            self._resizing = True
            self._resize_handle = handle
            anchor = self._opposite_corner(handle)
            self._resize_anchor_scene = self.mapToScene(anchor)
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._rotating:
            center = self._rect.center()
            vector = event.pos() - center
            angle = math.degrees(math.atan2(vector.y(), vector.x()))
            rotation = self._rotate_start_rotation + angle - self._rotate_start_angle
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                rotation = round(rotation / 15.0) * 15.0
            self.setRotation(rotation % 360)
            self._clamp_to_page()
            event.accept()
            return
        if self._resizing:
            self._resize_from_handle(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resizing = False
        self._resize_handle = None
        self._rotating = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
        new_state = self._geometry_state()
        if self._undo_geometry_state and self._undo_geometry_state != new_state and self.geometry_committed:
            self.geometry_committed(self.model_id, self._undo_geometry_state, new_state)
        self._undo_geometry_state = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            p = QPointF(value)
            min_x = -self._rect.left()
            min_y = -self._rect.top()
            max_x = self.page_rect.width() - self._rect.right()
            max_y = self.page_rect.height() - self._rect.bottom()
            p.setX(min(max(p.x(), min_x), max_x))
            p.setY(min(max(p.y(), min_y), max_y))
            if self.rotation() % 360:
                old_pos = self.pos()
                delta = p - old_pos
                bounds = self.sceneBoundingRect().translated(delta)
                if bounds.left() < self.page_rect.left():
                    p.setX(p.x() + self.page_rect.left() - bounds.left())
                if bounds.top() < self.page_rect.top():
                    p.setY(p.y() + self.page_rect.top() - bounds.top())
                if bounds.right() > self.page_rect.right():
                    p.setX(p.x() - (bounds.right() - self.page_rect.right()))
                if bounds.bottom() > self.page_rect.bottom():
                    p.setY(p.y() - (bounds.bottom() - self.page_rect.bottom()))
            return p
        return super().itemChange(change, value)

    def _opposite_corner(self, handle: str) -> QPointF:
        return {
            "tl": self._rect.bottomRight(),
            "tr": self._rect.bottomLeft(),
            "bl": self._rect.topRight(),
            "br": self._rect.topLeft(),
        }[handle]

    def _resize_from_handle(self, local: QPointF) -> None:
        if not self._resize_handle:
            return
        anchor = self._opposite_corner(self._resize_handle)
        dx = abs(local.x() - anchor.x())
        dy = abs(local.y() - anchor.y())
        min_w = 30.0
        min_h = min_w / max(0.01, self._aspect)
        new_w = max(min_w, dx)
        new_h = max(min_h, dy)
        if new_w / max(0.01, new_h) > self._aspect:
            new_w = new_h * self._aspect
        else:
            new_h = new_w / max(0.01, self._aspect)

        if self._resize_handle == "tl":
            new_rect = QRectF(anchor.x() - new_w, anchor.y() - new_h, new_w, new_h)
        elif self._resize_handle == "tr":
            new_rect = QRectF(anchor.x(), anchor.y() - new_h, new_w, new_h)
        elif self._resize_handle == "bl":
            new_rect = QRectF(anchor.x() - new_w, anchor.y(), new_w, new_h)
        else:
            new_rect = QRectF(anchor.x(), anchor.y(), new_w, new_h)

        self.prepareGeometryChange()
        self._rect = new_rect
        self.setTransformOriginPoint(self._rect.center())
        moved_anchor = self.mapToScene(self._opposite_corner(self._resize_handle))
        self.moveBy(self._resize_anchor_scene.x() - moved_anchor.x(), self._resize_anchor_scene.y() - moved_anchor.y())
        self._clamp_to_page()
        self.update()

    def _clamp_to_page(self) -> None:
        bounds = self.sceneBoundingRect()
        dx = 0.0
        dy = 0.0
        if bounds.left() < self.page_rect.left():
            dx = self.page_rect.left() - bounds.left()
        elif bounds.right() > self.page_rect.right():
            dx = self.page_rect.right() - bounds.right()
        if bounds.top() < self.page_rect.top():
            dy = self.page_rect.top() - bounds.top()
        elif bounds.bottom() > self.page_rect.bottom():
            dy = self.page_rect.bottom() - bounds.bottom()
        if dx or dy:
            self.moveBy(dx, dy)

    def _geometry_state(self) -> Tuple[float, float, float, float, float, float, float]:
        pos = self.pos()
        return (
            pos.x(),
            pos.y(),
            self._rect.x(),
            self._rect.y(),
            self._rect.width(),
            self._rect.height(),
            self.overlay_rotation(),
        )


class PreviewView(QGraphicsView):
    delete_pressed = Signal()

    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setBackgroundBrush(QBrush(QColor("#17191d")))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
            return
        super().keyPressEvent(event)


class PageListWidget(QListWidget):
    native_drop_finished = Signal(list, list)

    def dropEvent(self, event) -> None:
        old_order = self._ordered_page_ids()
        super().dropEvent(event)
        QTimer.singleShot(0, lambda: self.native_drop_finished.emit(old_order, self._ordered_page_ids()))

    def _ordered_page_ids(self) -> List[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]


class InsertPagesCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", models: List[PageModel], insert_at: int, text: str):
        super().__init__(text)
        self.window = window
        self.models = [deepcopy(model) for model in models]
        self.insert_at = insert_at

    def redo(self) -> None:
        self.window._insert_page_models_direct(self.models, self.insert_at)

    def undo(self) -> None:
        self.window._remove_page_ids_direct([model.id for model in self.models], select_row=max(0, self.insert_at - 1))


class DeletePagesCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", rows_and_models: List[Tuple[int, PageModel]]):
        super().__init__("Eliminar página")
        self.window = window
        self.rows_and_models = [(row, deepcopy(model)) for row, model in rows_and_models]

    def redo(self) -> None:
        self.window._remove_page_ids_direct([model.id for _, model in self.rows_and_models])

    def undo(self) -> None:
        for row, model in sorted(self.rows_and_models, key=lambda item: item[0]):
            self.window._insert_page_models_direct([model], row)


class RotatePagesCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", page_ids: List[str], delta: int):
        super().__init__("Rotar página")
        self.window = window
        self.page_ids = list(page_ids)
        self.delta = delta

    def redo(self) -> None:
        self.window._rotate_pages_direct(self.page_ids, self.delta)

    def undo(self) -> None:
        self.window._rotate_pages_direct(self.page_ids, -self.delta)


class ReorderPagesCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", old_order: List[str], new_order: List[str], skip_first_redo: bool = True):
        super().__init__("Reordenar páginas")
        self.window = window
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.skip_first_redo = skip_first_redo

    def redo(self) -> None:
        if self.skip_first_redo:
            self.skip_first_redo = False
            return
        self.window._apply_page_order(self.new_order)

    def undo(self) -> None:
        self.window._apply_page_order(self.old_order)


class InsertOverlayCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", page_id: str, overlay: OverlayModel):
        super().__init__("Insertar imagen")
        self.window = window
        self.page_id = page_id
        self.overlay = deepcopy(overlay)

    def redo(self) -> None:
        self.window._insert_overlay_direct(self.page_id, self.overlay)

    def undo(self) -> None:
        self.window._remove_overlay_ids_direct(self.page_id, [self.overlay.id])


class DeleteOverlaysCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", page_id: str, overlays: List[Tuple[int, OverlayModel]]):
        super().__init__("Eliminar imagen")
        self.window = window
        self.page_id = page_id
        self.overlays = [(index, deepcopy(overlay)) for index, overlay in overlays]

    def redo(self) -> None:
        self.window._remove_overlay_ids_direct(self.page_id, [overlay.id for _, overlay in self.overlays])

    def undo(self) -> None:
        self.window._insert_overlays_direct(self.page_id, self.overlays)


class UpdateOverlayCommand(QUndoCommand):
    def __init__(self, window: "MainWindow", page_id: str, before: OverlayModel, after: OverlayModel, text: str):
        super().__init__(text)
        self.window = window
        self.page_id = page_id
        self.before = deepcopy(before)
        self.after = deepcopy(after)

    def redo(self) -> None:
        self.window._replace_overlay_direct(self.page_id, self.after)

    def undo(self) -> None:
        self.window._replace_overlay_direct(self.page_id, self.before)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1420, 860)
        self.setMinimumSize(980, 650)

        self.pages: Dict[str, PageModel] = {}
        self.current_page_id: Optional[str] = None
        self.overlay_items: Dict[str, OverlayGraphicsItem] = {}
        self.thumbnail_cache: Dict[str, QPixmap] = {}
        self._changing_selection = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(20)

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
        paths, _ = QFileDialog.getOpenFileNames(self, "Seleccionar PDF", "", "Archivos PDF (*.pdf)")
        models: List[PageModel] = []
        for path in paths:
            try:
                doc = fitz.open(path)
                if doc.needs_pass:
                    QMessageBox.warning(self, APP_NAME, f"El PDF está protegido con contraseña:\n{path}")
                    doc.close()
                    continue
                for index in range(doc.page_count):
                    page = doc.load_page(index)
                    models.append(
                        PageModel(
                            id=uuid.uuid4().hex,
                            kind="pdf",
                            source=os.path.abspath(path),
                            page_index=index,
                            width_pt=page.rect.width,
                            height_pt=page.rect.height,
                            label=f"{Path(path).name}\nPág. {index + 1}",
                        )
                    )
                doc.close()
            except Exception as exc:
                QMessageBox.critical(self, APP_NAME, f"No se pudo abrir:\n{path}\n\n{exc}")
        if models:
            current_row = self.page_list.currentRow()
            insert_at = current_row + 1 if current_row >= 0 else self.page_list.count()
            self._insert_page_models_direct(models, insert_at)
            self.undo_stack.clear()

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
                    width, height = img.size
                if width >= height:
                    page_w, page_h = A4_PORTRAIT[1], A4_PORTRAIT[0]
                else:
                    page_w, page_h = A4_PORTRAIT
                models.append(
                    PageModel(
                        id=uuid.uuid4().hex,
                        kind="image",
                        source=os.path.abspath(path),
                        width_pt=page_w,
                        height_pt=page_h,
                        label=f"Imagen\n{Path(path).name}",
                    )
                )
            except Exception as exc:
                QMessageBox.warning(self, APP_NAME, f"No se pudo leer la imagen:\n{path}\n\n{exc}")
        if not models:
            return
        if was_empty:
            self._insert_page_models_direct(models, self.page_list.count())
            self.undo_stack.clear()
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
            path=os.path.abspath(path),
            x=(1 - norm_w) / 2,
            y=(1 - norm_h) / 2,
            w=norm_w,
            h=norm_h,
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
            pixmap = QPixmap(overlay.path)
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
            rotation = page.rotation % 360
            if page.kind == "pdf" and page.source is not None and page.page_index is not None:
                doc = fitz.open(page.source)
                src_page = doc.load_page(page.page_index)
                page_w, page_h = self._rotated_page_size(src_page.rect.width, src_page.rect.height, rotation)
                scale = target_long_edge / max(page_w, page_h)
                pix = src_page.get_pixmap(matrix=fitz.Matrix(scale, scale).prerotate(rotation), alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                doc.close()
                base = QPixmap.fromImage(qimg)
            else:
                page_w, page_h = self._rotated_page_size(page.width_pt, page.height_pt, rotation)
                scale = target_long_edge / max(page_w, page_h)
                width = max(1, int(page_w * scale))
                height = max(1, int(page_h * scale))
                base = QPixmap(width, height)
                base.fill(Qt.GlobalColor.white)
                if page.kind == "image" and page.source:
                    img = QPixmap(page.source)
                    if not img.isNull():
                        image_rect = self._fit_rect(
                            page.width_pt,
                            page.height_pt,
                            img.width(),
                            img.height(),
                            margin=max(8.0, min(page.width_pt, page.height_pt) * 0.035),
                        )
                        image_rect = self._rotate_rect(image_rect, page.width_pt, page.height_pt, rotation)
                        target_rect = QRectF(
                            image_rect.x0 * scale,
                            image_rect.y0 * scale,
                            image_rect.width * scale,
                            image_rect.height * scale,
                        )
                        if rotation:
                            img = img.transformed(
                                QTransform().rotate(rotation),
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        painter = QPainter(base)
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                        painter.drawPixmap(target_rect, img, img.rect())
                        painter.end()

            if include_overlays and page.overlays:
                painter = QPainter(base)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                for overlay in page.overlays:
                    img = QPixmap(overlay.path)
                    if img.isNull():
                        continue
                    if rotation:
                        img = img.transformed(
                            QTransform().rotate(rotation),
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    rect = QRectF(
                        overlay.x * base.width(),
                        overlay.y * base.height(),
                        overlay.w * base.width(),
                        overlay.h * base.height(),
                    )
                    painter.save()
                    painter.translate(rect.center())
                    painter.rotate(overlay.rotation)
                    centered = QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height())
                    painter.drawPixmap(centered, img, img.rect())
                    painter.restore()
                painter.end()
            return base
        except Exception:
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
        if delta % 360 == 90:
            overlay.x, overlay.y, overlay.w, overlay.h = (
                1.0 - overlay.y - overlay.h,
                overlay.x,
                overlay.h,
                overlay.w,
            )
        elif delta % 360 == 270:
            overlay.x, overlay.y, overlay.w, overlay.h = (
                overlay.y,
                1.0 - overlay.x - overlay.w,
                overlay.h,
                overlay.w,
            )
        elif delta % 360 == 180:
            overlay.x, overlay.y = (
                1.0 - overlay.x - overlay.w,
                1.0 - overlay.y - overlay.h,
            )
        overlay.x = min(max(overlay.x, 0.0), 1.0)
        overlay.y = min(max(overlay.y, 0.0), 1.0)
        overlay.w = min(max(overlay.w, 0.001), 1.0)
        overlay.h = min(max(overlay.h, 0.001), 1.0)

    @staticmethod
    def _rotated_page_size(width: float, height: float, rotation: int) -> Tuple[float, float]:
        if rotation % 180:
            return height, width
        return width, height

    @staticmethod
    def _rotate_rect(rect: fitz.Rect, width: float, height: float, rotation: int) -> fitz.Rect:
        rotation = rotation % 360
        if rotation == 90:
            return fitz.Rect(height - rect.y1, rect.x0, height - rect.y0, rect.x1)
        if rotation == 180:
            return fitz.Rect(width - rect.x1, height - rect.y1, width - rect.x0, height - rect.y0)
        if rotation == 270:
            return fitz.Rect(rect.y0, width - rect.x1, rect.y1, width - rect.x0)
        return rect

    @staticmethod
    def _rotated_rect_bounds(rect: fitz.Rect, rotation: float) -> fitz.Rect:
        angle = math.radians(rotation % 360)
        cos_a = abs(math.cos(angle))
        sin_a = abs(math.sin(angle))
        width = rect.width
        height = rect.height
        rotated_w = width * cos_a + height * sin_a
        rotated_h = width * sin_a + height * cos_a
        center_x = (rect.x0 + rect.x1) / 2
        center_y = (rect.y0 + rect.y1) / 2
        return fitz.Rect(
            center_x - rotated_w / 2,
            center_y - rotated_h / 2,
            center_x + rotated_w / 2,
            center_y + rotated_h / 2,
        )

    @staticmethod
    def _rotated_image_stream(path: str, rotation: float) -> bytes:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            with Image.open(path) as img:
                rotated = img.convert("RGBA").rotate(
                    -rotation,
                    expand=True,
                    resample=Image.Resampling.BICUBIC,
                )
                output = BytesIO()
                rotated.save(output, format="PNG")
                return output.getvalue()

        angle = math.radians(rotation % 360)
        cos_a = abs(math.cos(angle))
        sin_a = abs(math.sin(angle))
        width = max(1, math.ceil(pixmap.width() * cos_a + pixmap.height() * sin_a))
        height = max(1, math.ceil(pixmap.width() * sin_a + pixmap.height() * cos_a))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(width / 2, height / 2)
        painter.rotate(rotation)
        painter.drawPixmap(
            QRectF(-pixmap.width() / 2, -pixmap.height() / 2, pixmap.width(), pixmap.height()),
            pixmap,
            pixmap.rect(),
        )
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())

    @staticmethod
    def _fit_rect(page_w: float, page_h: float, image_w: int, image_h: int, margin: float = 20.0) -> fitz.Rect:
        avail_w = max(1.0, page_w - 2 * margin)
        avail_h = max(1.0, page_h - 2 * margin)
        ratio = min(avail_w / max(1, image_w), avail_h / max(1, image_h))
        w = image_w * ratio
        h = image_h * ratio
        x = (page_w - w) / 2
        y = (page_h - h) / 2
        return fitz.Rect(x, y, x + w, y + h)

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

        output = fitz.open()
        source_docs: Dict[str, fitz.Document] = {}
        try:
            for idx, page_id in enumerate(self.ordered_page_ids()):
                if progress.wasCanceled():
                    output.close()
                    return
                model = self.pages[page_id]
                rotation = model.rotation % 360
                fitz_rotation = (-rotation) % 360
                page_w, page_h = self._rotated_page_size(model.width_pt, model.height_pt, rotation)
                page = output.new_page(width=page_w, height=page_h)

                if model.kind == "pdf" and model.source is not None and model.page_index is not None:
                    if model.source not in source_docs:
                        source_docs[model.source] = fitz.open(model.source)
                    page.show_pdf_page(page.rect, source_docs[model.source], model.page_index, rotate=fitz_rotation)
                elif model.kind == "image" and model.source:
                    try:
                        with Image.open(model.source) as img:
                            iw, ih = img.size
                        rect = self._fit_rect(model.width_pt, model.height_pt, iw, ih)
                        rect = self._rotate_rect(rect, model.width_pt, model.height_pt, rotation)
                        page.insert_image(rect, filename=model.source, keep_proportion=True, rotate=fitz_rotation)
                    except Exception as exc:
                        raise RuntimeError(f"No se pudo insertar {model.source}: {exc}") from exc

                for overlay in model.overlays:
                    rect = fitz.Rect(
                        overlay.x * page_w,
                        overlay.y * page_h,
                        (overlay.x + overlay.w) * page_w,
                        (overlay.y + overlay.h) * page_h,
                    )
                    overlay_rotation = (rotation + overlay.rotation) % 360
                    if overlay_rotation:
                        bounds = self._rotated_rect_bounds(rect, overlay_rotation)
                        stream = self._rotated_image_stream(overlay.path, overlay_rotation)
                        page.insert_image(bounds, stream=stream, keep_proportion=False, overlay=True)
                    else:
                        page.insert_image(rect, filename=overlay.path, keep_proportion=False, overlay=True)

                progress.setValue(idx + 1)
                QApplication.processEvents()

            output.save(path, garbage=4, deflate=True, clean=True)
            output.close()
            for doc in source_docs.values():
                doc.close()
            progress.close()
            self.statusBar().showMessage(f"PDF exportado: {path}", 7000)
            QMessageBox.information(self, APP_NAME, f"PDF creado correctamente:\n{path}")
        except Exception as exc:
            try:
                output.close()
            except Exception:
                pass
            for doc in source_docs.values():
                try:
                    doc.close()
                except Exception:
                    pass
            progress.close()
            QMessageBox.critical(self, APP_NAME, f"No se pudo exportar el PDF.\n\n{exc}")

    def closeEvent(self, event) -> None:
        self.save_current_overlay_positions()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
