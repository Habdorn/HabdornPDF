import math

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap


def rotated_image_stream(path: str, rotation: float) -> bytes:
    try:
        from io import BytesIO

        with Image.open(path) as img:
            rotated = img.convert("RGBA").rotate(
                -rotation,
                expand=True,
                resample=Image.Resampling.BICUBIC,
            )
            buffer = BytesIO()
            rotated.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            raise RuntimeError(f"No se pudo abrir la imagen: {path}")
        angle = math.radians(rotation % 360)
        cos_a = abs(math.cos(angle))
        sin_a = abs(math.sin(angle))
        width = max(1, int(pixmap.width() * cos_a + pixmap.height() * sin_a))
        height = max(1, int(pixmap.width() * sin_a + pixmap.height() * cos_a))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(width / 2, height / 2)
        painter.rotate(rotation)
        painter.drawPixmap(
            QRectF(
                -pixmap.width() / 2,
                -pixmap.height() / 2,
                pixmap.width(),
                pixmap.height(),
            ),
            pixmap,
            pixmap.rect(),
        )
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())
