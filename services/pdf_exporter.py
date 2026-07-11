import math
from typing import Callable, Dict, Iterable, Optional

import fitz
from PIL import Image

from models.page_model import PageModel
from services.image_utils import rotated_image_stream
from services.pdf_renderer import (
    AssetPathResolver,
    fit_rect,
    resolve_model_path,
    rotate_rect,
    rotated_page_size,
)

ProgressCallback = Callable[[int], None]
CancelCallback = Callable[[], bool]


def rotated_rect_bounds(rect: fitz.Rect, rotation: float) -> fitz.Rect:
    angle = math.radians(rotation % 360)
    cos_a = abs(math.cos(angle))
    sin_a = abs(math.sin(angle))
    width = rect.width * cos_a + rect.height * sin_a
    height = rect.width * sin_a + rect.height * cos_a
    center = (rect.tl + rect.br) / 2
    return fitz.Rect(
        center.x - width / 2,
        center.y - height / 2,
        center.x + width / 2,
        center.y + height / 2,
    )


def _rotated_rect_bounds(rect: fitz.Rect, rotation: float) -> fitz.Rect:
    return rotated_rect_bounds(rect, rotation)


def export_pdf_document(
    pages: Dict[str, PageModel],
    ordered_page_ids: Iterable[str],
    path: str,
    progress_callback: ProgressCallback,
    is_cancelled: CancelCallback,
    resolve_asset_path: Optional[AssetPathResolver] = None,
) -> bool:
    output = fitz.open()
    source_docs: Dict[str, fitz.Document] = {}
    try:
        for index, page_id in enumerate(ordered_page_ids):
            if is_cancelled():
                return False

            model = pages[page_id]
            model_source = resolve_model_path(
                model.asset_id,
                model.source,
                resolve_asset_path,
            )
            rotation = model.rotation % 360
            fitz_rotation = (-rotation) % 360
            page_w, page_h = rotated_page_size(
                model.width_pt,
                model.height_pt,
                rotation,
            )
            page = output.new_page(width=page_w, height=page_h)

            if (
                model.kind == "pdf"
                and model_source is not None
                and model.page_index is not None
            ):
                if model_source not in source_docs:
                    source_docs[model_source] = fitz.open(model_source)
                page.show_pdf_page(
                    page.rect,
                    source_docs[model_source],
                    model.page_index,
                    rotate=fitz_rotation,
                )
            elif model.kind == "image" and model_source:
                try:
                    with Image.open(model_source) as image:
                        image_w, image_h = image.size
                    rect = fit_rect(
                        model.width_pt,
                        model.height_pt,
                        image_w,
                        image_h,
                    )
                    rect = rotate_rect(
                        rect,
                        model.width_pt,
                        model.height_pt,
                        rotation,
                    )
                    page.insert_image(
                        rect,
                        filename=model_source,
                        keep_proportion=True,
                        rotate=fitz_rotation,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"No se pudo insertar {model_source}: {exc}"
                    ) from exc

            for overlay in model.overlays:
                overlay_path = resolve_model_path(
                    overlay.asset_id,
                    overlay.path,
                    resolve_asset_path,
                )
                if not overlay_path:
                    raise RuntimeError(
                        "No se encontró la imagen interna del overlay."
                    )
                rect = fitz.Rect(
                    overlay.x * page_w,
                    overlay.y * page_h,
                    (overlay.x + overlay.w) * page_w,
                    (overlay.y + overlay.h) * page_h,
                )
                overlay_rotation = (rotation + overlay.rotation) % 360
                if overlay_rotation:
                    bounds = rotated_rect_bounds(rect, overlay_rotation)
                    stream = rotated_image_stream(
                        overlay_path,
                        overlay_rotation,
                    )
                    page.insert_image(
                        bounds,
                        stream=stream,
                        keep_proportion=False,
                        overlay=True,
                    )
                else:
                    page.insert_image(
                        rect,
                        filename=overlay_path,
                        keep_proportion=False,
                        overlay=True,
                    )

            progress_callback(index + 1)

        output.save(path, garbage=4, deflate=True, clean=True)
        return True
    finally:
        output.close()
        for document in source_docs.values():
            document.close()
