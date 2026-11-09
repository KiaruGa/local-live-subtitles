#!/usr/bin/env python3
"""Renders the application icon to assets/app.ico (multi-resolution PNG ICO)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "app.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.045
    radius = size * 0.235
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#7DB4FF"))
    gradient.setColorAt(0.5, QColor("#4A7FE0"))
    gradient.setColorAt(1.0, QColor("#22468F"))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, radius, radius)

    # Luminous glass edge.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 90), max(1.0, size * 0.012)))
    inner = rect.adjusted(size * 0.012, size * 0.012, -size * 0.012, -size * 0.012)
    painter.drawRoundedRect(inner, radius * 0.92, radius * 0.92)

    # Subtle top highlight.
    highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    highlight.setColorAt(0.0, QColor(255, 255, 255, 70))
    highlight.setColorAt(0.45, QColor(255, 255, 255, 0))
    painter.setBrush(highlight)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(inner, radius * 0.92, radius * 0.92)

    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", int(size * 0.34), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -size * 0.015)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "CC")
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(images: dict[int, bytes], path: Path) -> None:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = []
    payload = []
    for size in sorted(images):
        data = images[size]
        dimension = 0 if size >= 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        payload.append(data)
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"".join(entries) + b"".join(payload))


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 - required for font rendering
    images = {size: png_bytes(render(size)) for size in SIZES}
    write_ico(images, OUTPUT)
    print(f"Icon written: {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
