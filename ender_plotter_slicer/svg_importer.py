from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, radians, sin
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from svgpathtools import Arc, CubicBezier, Line, Path as SvgPath, QuadraticBezier, parse_path

from .geometry import AffineTransform, Point, Polyline, close_polyline_if_needed, combine_polylines_bbox, ensure_nonempty_polyline


CSS_PX_TO_MM = 25.4 / 96.0


class SVGImportError(RuntimeError):
    pass


@dataclass(slots=True)
class SVGImportResult:
    polylines: list[Polyline]
    source_name: str
    source_path: str
    notes: str = ""


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse_length(value: str | None) -> tuple[float | None, str]:
    if value is None:
        return None, ""
    match = re.fullmatch(r"\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)\s*", value)
    if not match:
        return None, ""
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    return number, unit


def _length_to_mm(value: str | None) -> float | None:
    number, unit = _parse_length(value)
    if number is None:
        return None
    if unit in ("", "px"):
        return number * CSS_PX_TO_MM
    if unit == "mm":
        return number
    if unit == "cm":
        return number * 10.0
    if unit == "in":
        return number * 25.4
    if unit == "pt":
        return number * 25.4 / 72.0
    if unit == "pc":
        return number * 25.4 / 6.0
    return number * CSS_PX_TO_MM


def _parse_float_list(raw: str) -> list[float]:
    parts = re.split(r"[\s,]+", raw.strip())
    return [float(part) for part in parts if part]


def _parse_points_attr(raw: str) -> list[Point]:
    values = _parse_float_list(raw)
    if len(values) < 4 or len(values) % 2 != 0:
        raise SVGImportError("Invalid points attribute in SVG polyline/polygon.")
    return [Point(values[index], values[index + 1]) for index in range(0, len(values), 2)]


def _flatten_svg_segment(segment, tolerance_mm: float = 0.35) -> list[Point]:
    if isinstance(segment, Line):
        return [
            Point(segment.start.real, segment.start.imag),
            Point(segment.end.real, segment.end.imag),
        ]
    try:
        length = max(segment.length(error=1e-4), tolerance_mm)
    except Exception:
        length = tolerance_mm * 5.0
    steps = max(8, int(length / max(0.05, tolerance_mm)) + 1)
    points = []
    for index in range(steps + 1):
        t = index / steps
        point = segment.point(t)
        points.append(Point(point.real, point.imag))
    return points


def _flatten_svg_path(path: SvgPath, tolerance_mm: float = 0.35) -> list[Polyline]:
    polylines: list[Polyline] = []
    current: list[Point] = []
    last_end: Point | None = None

    for segment in path:
        segment_points = _flatten_svg_segment(segment, tolerance_mm=tolerance_mm)
        if not current:
            current = [segment_points[0]]
        else:
            if current[-1].distance_to(segment_points[0]) > tolerance_mm * 0.5:
                polyline = ensure_nonempty_polyline(Polyline(current, closed=False))
                if polyline:
                    polylines.append(polyline)
                current = [segment_points[0]]
        current.extend(segment_points[1:])
        last_end = segment_points[-1]

    if current:
        closed = False
        if len(current) >= 3 and current[0].distance_to(current[-1]) <= tolerance_mm:
            current[-1] = current[0]
            closed = True
        polyline = ensure_nonempty_polyline(Polyline(current, closed=closed))
        if polyline:
            polylines.append(polyline)
    return polylines


def _parse_transform(transform: str | None) -> AffineTransform:
    if not transform:
        return AffineTransform.identity()

    token_re = re.compile(r"([a-zA-Z]+)\(([^)]+)\)")
    current = AffineTransform.identity()
    for name, args_raw in token_re.findall(transform):
        values = _parse_float_list(args_raw)
        name = name.lower()
        if name == "translate":
            dx = values[0] if values else 0.0
            dy = values[1] if len(values) > 1 else 0.0
            step = AffineTransform.translation(dx, dy)
        elif name == "scale":
            sx = values[0] if values else 1.0
            sy = values[1] if len(values) > 1 else sx
            step = AffineTransform.scale(sx, sy)
        elif name == "rotate":
            if not values:
                step = AffineTransform.identity()
            elif len(values) == 1:
                step = AffineTransform.rotation(values[0])
            else:
                angle = values[0]
                cx = values[1]
                cy = values[2] if len(values) > 2 else 0.0
                step = (
                    AffineTransform.translation(cx, cy)
                    .combine(AffineTransform.rotation(angle))
                    .combine(AffineTransform.translation(-cx, -cy))
                )
        elif name == "matrix" and len(values) == 6:
            step = AffineTransform.from_svg_matrix(*values)
        elif name == "skewx" and values:
            angle = radians(values[0])
            step = AffineTransform(1.0, 0.0, sin(angle) / cos(angle), 1.0, 0.0, 0.0)
        elif name == "skewy" and values:
            angle = radians(values[0])
            step = AffineTransform(1.0, sin(angle) / cos(angle), 0.0, 1.0, 0.0, 0.0)
        else:
            step = AffineTransform.identity()
        current = current.combine(step)
    return current


def _element_style(element: ET.Element) -> dict[str, str]:
    style: dict[str, str] = {}
    raw = element.attrib.get("style", "")
    for part in raw.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            style[key.strip()] = value.strip()
    return style


def _is_hidden(element: ET.Element) -> bool:
    style = _element_style(element)
    if element.attrib.get("display") == "none" or style.get("display") == "none":
        return True
    if element.attrib.get("visibility") == "hidden" or style.get("visibility") == "hidden":
        return True
    return False


def _element_to_local_polylines(element: ET.Element, tolerance_mm: float) -> list[Polyline]:
    tag = _local_name(element.tag)
    if tag == "path":
        d = element.attrib.get("d", "").strip()
        if not d:
            return []
        return _flatten_svg_path(parse_path(d), tolerance_mm=tolerance_mm)

    if tag == "line":
        x1 = float(element.attrib.get("x1", "0"))
        y1 = float(element.attrib.get("y1", "0"))
        x2 = float(element.attrib.get("x2", "0"))
        y2 = float(element.attrib.get("y2", "0"))
        polyline = ensure_nonempty_polyline(Polyline([Point(x1, y1), Point(x2, y2)], closed=False))
        return [polyline] if polyline else []

    if tag == "polyline":
        points = _parse_points_attr(element.attrib.get("points", ""))
        polyline = ensure_nonempty_polyline(Polyline(points, closed=False))
        return [polyline] if polyline else []

    if tag == "polygon":
        points = _parse_points_attr(element.attrib.get("points", ""))
        polyline = close_polyline_if_needed(Polyline(points, closed=False))
        polyline = ensure_nonempty_polyline(polyline)
        return [polyline] if polyline else []

    if tag == "rect":
        x = float(element.attrib.get("x", "0"))
        y = float(element.attrib.get("y", "0"))
        width = float(element.attrib.get("width", "0"))
        height = float(element.attrib.get("height", "0"))
        points = [
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
            Point(x, y),
        ]
        polyline = ensure_nonempty_polyline(Polyline(points, closed=True))
        return [polyline] if polyline else []

    if tag in {"circle", "ellipse"}:
        if tag == "circle":
            cx = float(element.attrib.get("cx", "0"))
            cy = float(element.attrib.get("cy", "0"))
            rx = float(element.attrib.get("r", "0"))
            ry = rx
        else:
            cx = float(element.attrib.get("cx", "0"))
            cy = float(element.attrib.get("cy", "0"))
            rx = float(element.attrib.get("rx", "0"))
            ry = float(element.attrib.get("ry", "0"))
        steps = max(24, int(2 * pi * max(rx, ry) / max(0.25, tolerance_mm)))
        points = []
        for step in range(steps + 1):
            angle = 2 * pi * step / steps
            points.append(Point(cx + rx * cos(angle), cy + ry * sin(angle)))
        polyline = ensure_nonempty_polyline(Polyline(points, closed=True))
        return [polyline] if polyline else []

    return []


def _apply_transform(polylines: list[Polyline], transform: AffineTransform) -> list[Polyline]:
    return [polyline.transformed(transform) for polyline in polylines]


def _infer_root_scale(root: ET.Element) -> AffineTransform:
    view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
    width_mm = _length_to_mm(root.attrib.get("width"))
    height_mm = _length_to_mm(root.attrib.get("height"))
    if len(view_box) == 4:
        _, _, vb_w, vb_h = [float(value) for value in view_box]
        scale_x = width_mm / vb_w if width_mm and vb_w else CSS_PX_TO_MM
        scale_y = height_mm / vb_h if height_mm and vb_h else CSS_PX_TO_MM
        return AffineTransform.scale(scale_x, scale_y)
    return AffineTransform.scale(CSS_PX_TO_MM, CSS_PX_TO_MM)


def import_svg_file(path: str | Path, tolerance_mm: float = 0.35) -> SVGImportResult:
    path = Path(path)
    if not path.exists():
        raise SVGImportError(f"SVG file '{path}' does not exist.")

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as exc:
        raise SVGImportError(f"Could not parse SVG file '{path}': {exc}") from exc

    root_scale = _infer_root_scale(root)
    collected: list[Polyline] = []

    def walk(element: ET.Element, inherited: AffineTransform) -> None:
        if _is_hidden(element):
            return
        local_transform = inherited.combine(_parse_transform(element.attrib.get("transform")))
        local_tag = _local_name(element.tag)
        if local_tag in {"svg", "g"}:
            for child in element:
                walk(child, local_transform)
            return
        try:
            local_polylines = _element_to_local_polylines(element, tolerance_mm=tolerance_mm)
        except Exception as exc:
            raise SVGImportError(f"Failed to import SVG element <{local_tag}>: {exc}") from exc
        collected.extend(_apply_transform(local_polylines, local_transform))
        for child in element:
            walk(child, local_transform)

    walk(root, root_scale)

    if not collected:
        raise SVGImportError("No plot-capable geometry found in SVG file.")

    bbox = combine_polylines_bbox(collected)
    if bbox is None:
        raise SVGImportError("Imported SVG geometry is empty after conversion.")

    # Normalise imported SVG so that its top-left corner becomes local origin.
    normalised = [polyline.transformed(AffineTransform.translation(-bbox.min_x, -bbox.min_y)) for polyline in collected]
    notes = "Imported supported SVG shape elements, flattened curves and applied simple transforms."
    return SVGImportResult(
        polylines=normalised,
        source_name=path.name,
        source_path=str(path),
        notes=notes,
    )
