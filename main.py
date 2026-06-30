from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QBrush, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
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


@dataclass
class PageModel:
    id: str
    kind: str  # pdf | image | blank
    source: Optional[str] = None
    page_index: Optional[int] = None
    width_pt: float = A4_PORTRAIT[0]
    height_pt: float = A4_PORTRAIT[1]
    label: str = "Página"
    overlays: List[OverlayModel] = field(default_factory=list)


class OverlayGraphicsItem(QGraphicsItem):
    HANDLE = 16.0

    def __init__(self, model_id: str, pixmap: QPixmap, rect: QRectF, page_rect: QRectF):
        super().__init__()
        self.model_id = model_id
        self.pixmap = pixmap
        self._rect = QRectF(rect)
        self.page_rect = QRectF(page_rect)
        self._resizing = False
        self._aspect = pixmap.width() / max(1, pixmap.height())
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(10)

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def boundingRect(self) -> QRectF:
        pad = 3.0
        return self._rect.adjusted(-pad, -pad, pad, pad)

    def handle_rect(self) -> QRectF:
        return QRectF(
            self._rect.right() - self.HANDLE,
            self._rect.bottom() - self.HANDLE,
            self.HANDLE,
            self.HANDLE,
        )

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(self._rect, self.pixmap, self.pixmap.rect())
        if self.isSelected():
            painter.setPen(QPen(QColor("#5aa9ff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(QBrush(QColor("#2f80ed")))
            painter.drawRect(self.handle_rect())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.handle_rect().contains(event.pos()):
            self._resizing = True
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            local = event.pos()
            new_w = max(40.0, local.x() - self._rect.left())
            new_h = max(30.0, new_w / max(0.01, self._aspect))

            max_w = self.page_rect.width() - self.pos().x() - self._rect.left()
            max_h = self.page_rect.height() - self.pos().y() - self._rect.top()
            if new_w > max_w:
                new_w = max_w
                new_h = new_w / max(0.01, self._aspect)
            if new_h > max_h:
                new_h = max_h
                new_w = new_h * self._aspect

            self.prepareGeometryChange()
            self._rect.setWidth(max(20.0, new_w))
            self._rect.setHeight(max(20.0, new_h))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resizing = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            p = QPointF(value)
            min_x = -self._rect.left()
            min_y = -self._rect.top()
            max_x = self.page_rect.width() - self._rect.right()
            max_y = self.page_rect.height() - self._rect.bottom()
            p.setX(min(max(p.x(), min_x), max_x))
            p.setY(min(max(p.y(), min_y), max_y))
            return p
        return super().itemChange(change, value)


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

        self.scene = QGraphicsScene(self)
        self.preview = PreviewView(self.scene)
        self.preview.delete_pressed.connect(self.delete_selected_overlays)

        self.page_list = QListWidget()
        self.page_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_list.setIconSize(QSize(150, 205))
        self.page_list.setGridSize(QSize(188, 248))
        self.page_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_list.setMovement(QListWidget.Movement.Snap)
        self.page_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.page_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.page_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.page_list.setSpacing(8)
        self.page_list.currentItemChanged.connect(self.on_page_changed)

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
        self._apply_style()
        self.statusBar().showMessage("Añade PDF o imágenes para comenzar")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Herramientas")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        actions = [
            ("+ PDF", self.add_pdfs),
            ("+ Imagen como página", self.add_images_as_pages),
            ("+ Página en blanco", self.add_blank_page),
            ("Insertar imagen", self.add_overlay_image),
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

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
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

    def _insert_page_models(self, models: List[PageModel]) -> None:
        if not models:
            return
        current_row = self.page_list.currentRow()
        insert_at = current_row + 1 if current_row >= 0 else self.page_list.count()
        for offset, model in enumerate(models):
            self.pages[model.id] = model
            item = QListWidgetItem(model.label)
            item.setData(Qt.ItemDataRole.UserRole, model.id)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setToolTip(model.label)
            self.page_list.insertItem(insert_at + offset, item)
            self._set_thumbnail(item, model)
        self.page_list.setCurrentRow(insert_at)
        self.statusBar().showMessage(f"{len(models)} página(s) añadida(s)", 4000)

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
        self._insert_page_models(models)

    def add_images_as_pages(self) -> None:
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
        self._insert_page_models(models)

    def add_blank_page(self) -> None:
        model = PageModel(
            id=uuid.uuid4().hex,
            kind="blank",
            width_pt=A4_PORTRAIT[0],
            height_pt=A4_PORTRAIT[1],
            label="Página en blanco\nA4",
        )
        self._insert_page_models([model])

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
        norm_w = 0.42
        norm_h = norm_w * (page.width_pt / page.height_pt) / ratio
        if norm_h > 0.55:
            norm_h = 0.55
            norm_w = norm_h * ratio * (page.height_pt / page.width_pt)
        overlay = OverlayModel(
            id=uuid.uuid4().hex,
            path=os.path.abspath(path),
            x=(1 - norm_w) / 2,
            y=(1 - norm_h) / 2,
            w=norm_w,
            h=norm_h,
        )
        page.overlays.append(overlay)
        self.load_page_into_preview(page.id)
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
        page.overlays = [o for o in page.overlays if o.id not in selected_ids]
        self.load_page_into_preview(page.id)
        self._refresh_current_thumbnail()

    def delete_selected_pages(self) -> None:
        selected = self.page_list.selectedItems()
        if not selected:
            return
        self.save_current_overlay_positions()
        rows = sorted((self.page_list.row(item) for item in selected), reverse=True)
        removed_ids = []
        for row in rows:
            item = self.page_list.takeItem(row)
            if item:
                removed_ids.append(item.data(Qt.ItemDataRole.UserRole))
        for page_id in removed_ids:
            self.pages.pop(page_id, None)
            self.thumbnail_cache.pop(page_id, None)
        self.current_page_id = None
        self.scene.clear()
        if self.page_list.count():
            self.page_list.setCurrentRow(min(rows[-1] if rows else 0, self.page_list.count() - 1))
        else:
            self.statusBar().showMessage("Añade PDF o imágenes para comenzar")

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
        self._refresh_current_thumbnail()

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
        for overlay in page.overlays:
            pixmap = QPixmap(overlay.path)
            if pixmap.isNull():
                continue
            rect = QRectF(0, 0, overlay.w * page_rect.width(), overlay.h * page_rect.height())
            item = OverlayGraphicsItem(overlay.id, pixmap, rect, page_rect)
            item.setPos(overlay.x * page_rect.width(), overlay.y * page_rect.height())
            self.scene.addItem(item)
            self.overlay_items[overlay.id] = item

        self.preview.resetTransform()
        self.preview.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.statusBar().showMessage(page.label.replace("\n", " - "))

    def render_page_pixmap(self, page: PageModel, target_long_edge: int = 900, include_overlays: bool = True) -> QPixmap:
        try:
            if page.kind == "pdf" and page.source is not None and page.page_index is not None:
                doc = fitz.open(page.source)
                src_page = doc.load_page(page.page_index)
                scale = target_long_edge / max(src_page.rect.width, src_page.rect.height)
                pix = src_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                doc.close()
                base = QPixmap.fromImage(qimg)
            else:
                scale = target_long_edge / max(page.width_pt, page.height_pt)
                width = max(1, int(page.width_pt * scale))
                height = max(1, int(page.height_pt * scale))
                base = QPixmap(width, height)
                base.fill(Qt.GlobalColor.white)
                if page.kind == "image" and page.source:
                    img = QPixmap(page.source)
                    if not img.isNull():
                        margin = max(12, int(min(width, height) * 0.035))
                        fitted = img.scaled(
                            width - 2 * margin,
                            height - 2 * margin,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        painter = QPainter(base)
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                        x = (width - fitted.width()) // 2
                        y = (height - fitted.height()) // 2
                        painter.drawPixmap(x, y, fitted)
                        painter.end()

            if include_overlays and page.overlays:
                painter = QPainter(base)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                for overlay in page.overlays:
                    img = QPixmap(overlay.path)
                    if img.isNull():
                        continue
                    rect = QRectF(
                        overlay.x * base.width(),
                        overlay.y * base.height(),
                        overlay.w * base.width(),
                        overlay.h * base.height(),
                    )
                    painter.drawPixmap(rect, img, img.rect())
                painter.end()
            return base
        except Exception:
            placeholder = QPixmap(480, 640)
            placeholder.fill(QColor("#ffffff"))
            return placeholder

    def _set_thumbnail(self, item: QListWidgetItem, page: PageModel) -> None:
        pixmap = self.render_page_pixmap(page, target_long_edge=430, include_overlays=True)
        thumb = QPixmap(150, 205)
        thumb.fill(QColor("#111318"))
        fitted = pixmap.scaled(
            144,
            199,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
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

    def _refresh_current_thumbnail(self) -> None:
        if not self.current_page_id:
            return
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == self.current_page_id:
                self._set_thumbnail(item, self.pages[self.current_page_id])
                break

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
                page = output.new_page(width=model.width_pt, height=model.height_pt)

                if model.kind == "pdf" and model.source is not None and model.page_index is not None:
                    if model.source not in source_docs:
                        source_docs[model.source] = fitz.open(model.source)
                    page.show_pdf_page(page.rect, source_docs[model.source], model.page_index)
                elif model.kind == "image" and model.source:
                    try:
                        with Image.open(model.source) as img:
                            iw, ih = img.size
                        rect = self._fit_rect(model.width_pt, model.height_pt, iw, ih)
                        page.insert_image(rect, filename=model.source, keep_proportion=True)
                    except Exception as exc:
                        raise RuntimeError(f"No se pudo insertar {model.source}: {exc}") from exc

                for overlay in model.overlays:
                    rect = fitz.Rect(
                        overlay.x * model.width_pt,
                        overlay.y * model.height_pt,
                        (overlay.x + overlay.w) * model.width_pt,
                        (overlay.y + overlay.h) * model.height_pt,
                    )
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
