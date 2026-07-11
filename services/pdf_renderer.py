from typing import Callable, Optional, Tuple

import fitz
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QTransform

from models.overlay_model import OverlayModel
from models.page_model import PageModel
from services.asset_manager import AssetManagerError

AssetPathResolver = Callable[[str], str]


def resolve_model_path(
    asset_id: Optional[str],
    legacy_path: Optional[str],
    resolve_asset_path: Optional[AssetPathResolver],
) -> Optional[str]:
    if asset_id is not None:
        if resolve_asset_path is None:
            raise RuntimeError(
                "No se configuró un resolvedor para el asset interno."
            )
        return resolve_asset_path(asset_id)
    # Compatibilidad temporal con modelos creados antes de los assets embebidos.
    return legacy_path


def rotate_overlay(overlay: OverlayModel, delta: int) -> None:
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


def rotated_page_size(
    width: float,
    height: float,
    rotation: int,
) -> Tuple[float, float]:
    if rotation % 180:
        return height, width
    return width, height


def rotate_rect(
    rect: fitz.Rect,
    width: float,
    height: float,
    rotation: int,
) -> fitz.Rect:
    rotation = rotation % 360
    if rotation == 90:
        return fitz.Rect(height - rect.y1, rect.x0, height - rect.y0, rect.x1)
    if rotation == 180:
        return fitz.Rect(
            width - rect.x1,
            height - rect.y1,
            width - rect.x0,
            height - rect.y0,
        )
    if rotation == 270:
        return fitz.Rect(rect.y0, width - rect.x1, rect.y1, width - rect.x0)
    return fitz.Rect(rect)


def fit_rect(
    page_w: float,
    page_h: float,
    image_w: int,
    image_h: int,
    margin: float = 20.0,
) -> fitz.Rect:
    avail_w = max(1.0, page_w - 2 * margin)
    avail_h = max(1.0, page_h - 2 * margin)
    ratio = min(
        avail_w / max(1, image_w),
        avail_h / max(1, image_h),
    )
    width = image_w * ratio
    height = image_h * ratio
    x = (page_w - width) / 2
    y = (page_h - height) / 2
    return fitz.Rect(x, y, x + width, y + height)


def render_page_pixmap(
    page: PageModel,
    target_long_edge: int = 900,
    include_overlays: bool = True,
    resolve_asset_path: Optional[AssetPathResolver] = None,
) -> QPixmap:
    try:
        rotation = page.rotation % 360
        page_source = resolve_model_path(
            page.asset_id,
            page.source,
            resolve_asset_path,
        )
        if (
            page.kind == "pdf"
            and page_source is not None
            and page.page_index is not None
        ):
            doc = fitz.open(page_source)
            src_page = doc.load_page(page.page_index)
            page_w, page_h = rotated_page_size(
                src_page.rect.width,
                src_page.rect.height,
                rotation,
            )
            scale = target_long_edge / max(page_w, page_h)
            pix = src_page.get_pixmap(
                matrix=fitz.Matrix(scale, scale).prerotate(rotation),
                alpha=False,
            )
            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            doc.close()
            base = QPixmap.fromImage(qimg)
        else:
            page_w, page_h = rotated_page_size(
                page.width_pt,
                page.height_pt,
                rotation,
            )
            scale = target_long_edge / max(page_w, page_h)
            width = max(1, int(page_w * scale))
            height = max(1, int(page_h * scale))
            base = QPixmap(width, height)
            base.fill(Qt.GlobalColor.white)
            if page.kind == "image" and page_source:
                img = QPixmap(page_source)
                if not img.isNull():
                    image_rect = fit_rect(
                        page.width_pt,
                        page.height_pt,
                        img.width(),
                        img.height(),
                        margin=max(
                            8.0,
                            min(page.width_pt, page.height_pt) * 0.035,
                        ),
                    )
                    image_rect = rotate_rect(
                        image_rect,
                        page.width_pt,
                        page.height_pt,
                        rotation,
                    )
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
                    painter.setRenderHint(
                        QPainter.RenderHint.SmoothPixmapTransform,
                        True,
                    )
                    painter.drawPixmap(target_rect, img, img.rect())
                    painter.end()

        if include_overlays and page.overlays:
            painter = QPainter(base)
            painter.setRenderHint(
                QPainter.RenderHint.SmoothPixmapTransform,
                True,
            )
            for overlay in page.overlays:
                overlay_path = resolve_model_path(
                    overlay.asset_id,
                    overlay.path,
                    resolve_asset_path,
                )
                img = QPixmap(overlay_path or "")
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
                centered = QRectF(
                    -rect.width() / 2,
                    -rect.height() / 2,
                    rect.width(),
                    rect.height(),
                )
                painter.drawPixmap(centered, img, img.rect())
                painter.restore()
            painter.end()
        return base
    except AssetManagerError:
        raise
    except Exception:
        placeholder = QPixmap(480, 640)
        placeholder.fill(QColor("#ffffff"))
        return placeholder
