from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose
from typing import Iterable

from .document import PlotterDocument
from .geometry import AffineTransform, Point, Polyline
from .preview import PreviewBundle, PreviewSegment


@dataclass(slots=True)
class PlotStats:
    draw_length_mm: float = 0.0
    travel_length_mm: float = 0.0
    path_count: int = 0


@dataclass(slots=True)
class GCodeResult:
    gcode: str
    lines: list[str]
    preview: PreviewBundle
    stats: PlotStats


def _point_key(point: Point) -> tuple[float, float]:
    return (round(point.x, 4), round(point.y, 4))


def _map_point_to_machine(document: PlotterDocument, point: Point) -> Point:
    profile = document.profile
    x = point.x
    y = point.y

    if profile.origin_mode == "top_left":
        y = document.page.height_mm - y

    if profile.swap_xy:
        x, y = y, x
    if profile.mirror_x:
        x = document.page.width_mm - x
    if profile.mirror_y:
        y = document.page.height_mm - y

    if profile.output_rotation_deg:
        centre = Point(document.page.width_mm / 2.0, document.page.height_mm / 2.0)
        rot = (
            AffineTransform.translation(centre.x, centre.y)
            .combine(AffineTransform.rotation(profile.output_rotation_deg))
            .combine(AffineTransform.translation(-centre.x, -centre.y))
        )
        rotated = rot.apply(Point(x, y))
        x = rotated.x
        y = rotated.y

    return Point(profile.work_offset_x_mm + x, profile.work_offset_y_mm + y)


def _collect_world_polylines(document: PlotterDocument) -> list[Polyline]:
    polylines: list[Polyline] = []
    for obj in document.visible_objects():
        polylines.extend(
            [
                polyline.simplified(document.gcode.curve_tolerance_mm * 0.25)
                for polyline in obj.world_polylines()
                if polyline.is_valid()
            ]
        )
    return [polyline for polyline in polylines if polyline.length() > 0.01]


def _optimise_order(polylines: list[Polyline]) -> list[Polyline]:
    if not polylines:
        return []

    remaining = polylines[:]
    ordered = [remaining.pop(0)]
    current_point = ordered[0].points[-1]

    while remaining:
        best_index = 0
        best_reverse = False
        best_distance = float("inf")
        for index, polyline in enumerate(remaining):
            start_distance = current_point.distance_to(polyline.points[0])
            end_distance = current_point.distance_to(polyline.points[-1])
            if start_distance < best_distance:
                best_distance = start_distance
                best_index = index
                best_reverse = False
            if end_distance < best_distance:
                best_distance = end_distance
                best_index = index
                best_reverse = True
        next_polyline = remaining.pop(best_index)
        if best_reverse:
            next_polyline = next_polyline.reversed()
        ordered.append(next_polyline)
        current_point = next_polyline.points[-1]
    return ordered


class _GCodeBuilder:
    def __init__(self, result_lines: list[str], preview: PreviewBundle, stats: PlotStats, document: PlotterDocument) -> None:
        self.lines = result_lines
        self.preview = preview
        self.stats = stats
        self.document = document
        self.current_xy: Point | None = None
        self.current_z: float | None = None
        self.pen_down = False

    def _fmt(self, value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def comment(self, text: str) -> None:
        if self.document.gcode.include_comments:
            self.lines.append(f"; {text}")

    def raw(self, line: str) -> None:
        if line.strip():
            self.lines.append(line.rstrip())

    def z_move(self, z: float, comment: str | None = None) -> None:
        if self.current_z is not None and isclose(self.current_z, z, abs_tol=1e-5):
            return
        line = f"G1 Z{self._fmt(z)} F{self._fmt(self.document.profile.z_feed_mm_min)}"
        if comment and self.document.gcode.include_comments:
            line += f" ; {comment}"
        self.lines.append(line)
        self.current_z = z

    def pen_raise_to_retract(self) -> None:
        profile = self.document.profile
        if self.pen_down:
            self.z_move(profile.pen_up_z_mm, "pen up")
            self.pen_down = False
        self.z_move(profile.retract_z_mm, "retract")

    def pen_lower(self) -> None:
        profile = self.document.profile
        self.z_move(profile.pen_up_z_mm, "pre-load")
        self.z_move(profile.pen_down_z_mm, "pen down")
        self.pen_down = True

    def travel_to(self, point: Point) -> None:
        if self.current_xy is not None:
            self.stats.travel_length_mm += self.current_xy.distance_to(point)
            self.preview.segments.append(PreviewSegment(self.current_xy, point, is_draw=False))
        self.lines.append(
            f"G0 X{self._fmt(point.x)} Y{self._fmt(point.y)} F{self._fmt(self.document.profile.travel_feed_mm_min)}"
        )
        self.current_xy = point

    def draw_to(self, point: Point) -> None:
        if self.current_xy is not None:
            self.stats.draw_length_mm += self.current_xy.distance_to(point)
            self.preview.segments.append(PreviewSegment(self.current_xy, point, is_draw=True))
        self.lines.append(
            f"G1 X{self._fmt(point.x)} Y{self._fmt(point.y)} F{self._fmt(self.document.profile.plot_feed_mm_min)}"
        )
        self.current_xy = point


def generate_gcode(document: PlotterDocument) -> GCodeResult:
    polylines = _collect_world_polylines(document)
    if document.gcode.optimize_order:
        polylines = _optimise_order(polylines)

    mapped_polylines = [
        Polyline([_map_point_to_machine(document, point) for point in polyline.points], closed=polyline.closed)
        for polyline in polylines
    ]

    lines: list[str] = []
    preview = PreviewBundle()
    stats = PlotStats(path_count=len(mapped_polylines))
    builder = _GCodeBuilder(lines, preview, stats, document)
    profile = document.profile

    builder.comment(f"Generated by Ender Plotter Slicer for profile '{profile.name}'")
    for line in profile.start_gcode.splitlines():
        builder.raw(line)

    if profile.home_enabled:
        builder.raw("G28")

    builder.z_move(profile.retract_z_mm, "initial retract")
    builder.travel_to(Point(profile.safe_start_x_mm, profile.safe_start_y_mm))

    previous_end: Point | None = builder.current_xy
    for index, polyline in enumerate(mapped_polylines, start=1):
        if not polyline.points:
            continue
        start = polyline.points[0]
        end = polyline.points[-1]
        keep_pen_down = (
            document.gcode.keep_pen_down_on_touching_paths
            and previous_end is not None
            and previous_end.distance_to(start) <= document.gcode.join_tolerance_mm
        )
        if not keep_pen_down:
            builder.pen_raise_to_retract()
            builder.comment(f"path {index}/{len(mapped_polylines)}")
            builder.travel_to(start)
            builder.pen_lower()
        elif not builder.pen_down:
            builder.pen_lower()

        for point in polyline.points[1:]:
            builder.draw_to(point)

        previous_end = end

    builder.pen_raise_to_retract()
    builder.travel_to(Point(profile.safe_start_x_mm, profile.safe_start_y_mm))
    for line in profile.end_gcode.splitlines():
        builder.raw(line)

    gcode = "\n".join(lines) + "\n"
    return GCodeResult(gcode=gcode, lines=lines, preview=preview, stats=stats)
