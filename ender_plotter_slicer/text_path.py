from __future__ import annotations

from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath
from matplotlib.text import TextToPath

from .geometry import Point, Polyline, ensure_nonempty_polyline


_PT_TO_MM = 25.4 / 72.0
_MM_TO_PT = 72.0 / 25.4


def _mpl_path_to_polylines(path: MplPath, translate_x_mm: float = 0.0, translate_y_mm: float = 0.0) -> list[Polyline]:
    current: list[Point] = []
    polylines: list[Polyline] = []
    for vertices, code in path.iter_segments(curves=False):
        if code == MplPath.MOVETO:
            if len(current) >= 2:
                polyline = ensure_nonempty_polyline(Polyline(current, closed=False))
                if polyline:
                    polylines.append(polyline)
            x, y = vertices
            current = [Point(float(x) * _PT_TO_MM + translate_x_mm, -float(y) * _PT_TO_MM + translate_y_mm)]
        elif code == MplPath.LINETO:
            x, y = vertices
            current.append(Point(float(x) * _PT_TO_MM + translate_x_mm, -float(y) * _PT_TO_MM + translate_y_mm))
        elif code == MplPath.CLOSEPOLY:
            if current:
                current.append(current[0])
                polyline = ensure_nonempty_polyline(Polyline(current, closed=True))
                if polyline:
                    polylines.append(polyline)
            current = []
    if len(current) >= 2:
        polyline = ensure_nonempty_polyline(Polyline(current, closed=False))
        if polyline:
            polylines.append(polyline)
    return polylines


def available_font_families() -> list[str]:
    from matplotlib import font_manager

    names = sorted({entry.name for entry in font_manager.fontManager.ttflist})
    return names


def text_to_polylines(
    text: str,
    font_family: str,
    font_size_mm: float,
    letter_spacing_mm: float = 0.0,
    line_spacing: float = 1.2,
) -> list[Polyline]:
    text = text or ""
    if not text.strip():
        return []

    size_pt = max(0.5, font_size_mm * _MM_TO_PT)
    letter_spacing_pt = letter_spacing_mm * _MM_TO_PT
    prop = FontProperties(family=font_family, size=size_pt)
    text_to_path = TextToPath()

    output: list[Polyline] = []
    lines = text.splitlines() or [text]
    line_height_mm = font_size_mm * line_spacing

    for line_index, line in enumerate(lines):
        cursor_x_pt = 0.0
        line_offset_y_mm = line_index * line_height_mm
        for character in line:
            width_pt, _, _ = text_to_path.get_text_width_height_descent(character or " ", prop, ismath=False)
            if character.strip():
                char_path = TextPath((cursor_x_pt, 0.0), character, size=size_pt, prop=prop, usetex=False)
                output.extend(_mpl_path_to_polylines(char_path, translate_y_mm=line_offset_y_mm))
            cursor_x_pt += width_pt + letter_spacing_pt
        if not line:
            cursor_x_pt = 0.0

    return output
