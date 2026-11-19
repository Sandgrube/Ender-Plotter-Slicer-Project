"""Render the actual plot paths at a physical pencil width, without Qt."""
from __future__ import annotations

from PIL import Image, ImageDraw

from .geometry import Polyline


def render_pencil_preview(
    polylines: list[Polyline], width_mm: float, height_mm: float,
    pencil_width_mm: float = 0.30, stroke_opacity: float = 0.65,
    max_pixels: int = 1200, cancel=None,
) -> Image.Image:
    scale = max_pixels / max(width_mm, height_mm)
    supersampling = 3
    size = (max(1, round(width_mm * scale)), max(1, round(height_mm * scale)))
    image = Image.new("RGB", (size[0] * supersampling, size[1] * supersampling), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    factor = scale * supersampling
    stroke_width = max(1, round(pencil_width_mm * factor))
    color = (0, 0, 0, round(255 * stroke_opacity))
    for index, line in enumerate(polylines):
        if cancel and index % 128 == 0 and cancel():
            from .raster_importer import RasterImportCancelled
            raise RasterImportCancelled("Preview cancelled.")
        points = [(p.x * factor, p.y * factor) for p in line.points]
        if line.closed and points:
            points.append(points[0])
        if len(points) >= 2:
            draw.line(points, fill=color, width=stroke_width, joint="curve")
    return image.resize(size, Image.Resampling.LANCZOS)
