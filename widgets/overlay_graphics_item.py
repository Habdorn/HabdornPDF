import math
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem


class OverlayGraphicsItem(QGraphicsItem):
    HANDLE = 16.0
    ROTATE_OFFSET = 32.0

    def __init__(
        self,
        model_id: str,
        pixmap: QPixmap,
        rect: QRectF,
        page_rect: QRectF,
        rotation: float = 0.0,
    ):
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
        return QRectF(p.x() - half, p.y() - half, self.HANDLE, self.HANDLE)

    def rotate_handle_rect(self) -> QRectF:
        half = self.HANDLE / 2.0
        center = QPointF(
            self._rect.center().x(),
            self._rect.top() - self.ROTATE_OFFSET,
        )
        return QRectF(
            center.x() - half,
            center.y() - half,
            self.HANDLE,
            self.HANDLE,
        )

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
            self._rotate_start_angle = math.degrees(
                math.atan2(vector.y(), vector.x())
            )
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
            rotation = (
                self._rotate_start_rotation + angle - self._rotate_start_angle
            )
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
        if (
            self._undo_geometry_state
            and self._undo_geometry_state != new_state
            and self.geometry_committed
        ):
            self.geometry_committed(
                self.model_id,
                self._undo_geometry_state,
                new_state,
            )
        self._undo_geometry_state = None

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.scene()
        ):
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
                    p.setX(
                        p.x() - (bounds.right() - self.page_rect.right())
                    )
                if bounds.bottom() > self.page_rect.bottom():
                    p.setY(
                        p.y() - (bounds.bottom() - self.page_rect.bottom())
                    )
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
            new_rect = QRectF(
                anchor.x() - new_w,
                anchor.y() - new_h,
                new_w,
                new_h,
            )
        elif self._resize_handle == "tr":
            new_rect = QRectF(anchor.x(), anchor.y() - new_h, new_w, new_h)
        elif self._resize_handle == "bl":
            new_rect = QRectF(anchor.x() - new_w, anchor.y(), new_w, new_h)
        else:
            new_rect = QRectF(anchor.x(), anchor.y(), new_w, new_h)

        self.prepareGeometryChange()
        self._rect = new_rect
        self.setTransformOriginPoint(self._rect.center())
        moved_anchor = self.mapToScene(
            self._opposite_corner(self._resize_handle)
        )
        self.moveBy(
            self._resize_anchor_scene.x() - moved_anchor.x(),
            self._resize_anchor_scene.y() - moved_anchor.y(),
        )
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

    def _geometry_state(
        self,
    ) -> Tuple[float, float, float, float, float, float, float]:
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
