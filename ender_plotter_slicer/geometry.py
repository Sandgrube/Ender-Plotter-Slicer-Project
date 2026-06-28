from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, hypot, radians, sin
from typing import Iterable, Sequence


EPSILON = 1e-9


@dataclass(slots=True)
class Point:
    x: float
    y: float

    def translated(self, dx: float, dy: float) -> "Point":
        return Point(self.x + dx, self.y + dy)

    def distance_to(self, other: "Point") -> float:
        return hypot(self.x - other.x, self.y - other.y)

    def as_list(self) -> list[float]:
        return [round(self.x, 6), round(self.y, 6)]


@dataclass(slots=True)
class BoundingBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center(self) -> Point:
        return Point((self.min_x + self.max_x) * 0.5, (self.min_y + self.max_y) * 0.5)

    def expanded(self, margin: float) -> "BoundingBox":
        return BoundingBox(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )

    def contains_point(self, point: Point) -> bool:
        return (
            self.min_x - EPSILON <= point.x <= self.max_x + EPSILON
            and self.min_y - EPSILON <= point.y <= self.max_y + EPSILON
        )

    def intersects(self, other: "BoundingBox") -> bool:
        return not (
            self.max_x < other.min_x
            or self.min_x > other.max_x
            or self.max_y < other.min_y
            or self.min_y > other.max_y
        )

    def union(self, other: "BoundingBox") -> "BoundingBox":
        return BoundingBox(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )

    @staticmethod
    def from_points(points: Sequence[Point]) -> "BoundingBox":
        if not points:
            raise ValueError("Cannot compute a bounding box from no points.")
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))


@dataclass(slots=True)
class Polyline:
    points: list[Point] = field(default_factory=list)
    closed: bool = False

    def is_valid(self) -> bool:
        return len(self.points) >= 2

    def transformed(self, transform: "AffineTransform") -> "Polyline":
        return Polyline([transform.apply(p) for p in self.points], self.closed)

    def reversed(self) -> "Polyline":
        return Polyline(list(reversed(self.points)), self.closed)

    def length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        total = 0.0
        for first, second in zip(self.points[:-1], self.points[1:]):
            total += first.distance_to(second)
        if self.closed and len(self.points) > 2:
            total += self.points[-1].distance_to(self.points[0])
        return total

    def bbox(self) -> BoundingBox:
        return BoundingBox.from_points(self.points)

    def simplified(self, tolerance: float = 0.02) -> "Polyline":
        if len(self.points) < 2:
            return Polyline(list(self.points), self.closed)
        simplified_points = [self.points[0]]
        for point in self.points[1:]:
            if point.distance_to(simplified_points[-1]) >= tolerance:
                simplified_points.append(point)
        if len(simplified_points) == 1 and len(self.points) > 1:
            simplified_points.append(self.points[-1])
        if self.closed and simplified_points[0].distance_to(simplified_points[-1]) < tolerance:
            simplified_points[-1] = simplified_points[0]
        return Polyline(simplified_points, self.closed)

    def as_serializable(self) -> dict:
        return {
            "closed": self.closed,
            "points": [point.as_list() for point in self.points],
        }

    @staticmethod
    def from_serializable(data: dict) -> "Polyline":
        pts = [Point(float(pair[0]), float(pair[1])) for pair in data.get("points", [])]
        return Polyline(points=pts, closed=bool(data.get("closed", False)))


@dataclass(slots=True)
class AffineTransform:
    m11: float = 1.0
    m12: float = 0.0
    m21: float = 0.0
    m22: float = 1.0
    dx: float = 0.0
    dy: float = 0.0

    def apply(self, point: Point) -> Point:
        return Point(
            self.m11 * point.x + self.m21 * point.y + self.dx,
            self.m12 * point.x + self.m22 * point.y + self.dy,
        )

    def combine(self, other: "AffineTransform") -> "AffineTransform":
        return AffineTransform(
            m11=self.m11 * other.m11 + self.m21 * other.m12,
            m12=self.m12 * other.m11 + self.m22 * other.m12,
            m21=self.m11 * other.m21 + self.m21 * other.m22,
            m22=self.m12 * other.m21 + self.m22 * other.m22,
            dx=self.m11 * other.dx + self.m21 * other.dy + self.dx,
            dy=self.m12 * other.dx + self.m22 * other.dy + self.dy,
        )

    @staticmethod
    def identity() -> "AffineTransform":
        return AffineTransform()

    @staticmethod
    def translation(dx: float, dy: float) -> "AffineTransform":
        return AffineTransform(dx=dx, dy=dy)

    @staticmethod
    def scale(sx: float, sy: float | None = None) -> "AffineTransform":
        sy = sx if sy is None else sy
        return AffineTransform(m11=sx, m22=sy)

    @staticmethod
    def rotation(degrees: float) -> "AffineTransform":
        angle = radians(degrees)
        c = cos(angle)
        s = sin(angle)
        return AffineTransform(m11=c, m12=s, m21=-s, m22=c)

    @staticmethod
    def mirror(horizontal: bool = False, vertical: bool = False) -> "AffineTransform":
        sx = -1.0 if horizontal else 1.0
        sy = -1.0 if vertical else 1.0
        return AffineTransform.scale(sx, sy)

    @staticmethod
    def from_svg_matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> "AffineTransform":
        return AffineTransform(m11=a, m12=b, m21=c, m22=d, dx=e, dy=f)


def combine_polylines_bbox(polylines: Iterable[Polyline]) -> BoundingBox | None:
    bbox: BoundingBox | None = None
    for polyline in polylines:
        if not polyline.points:
            continue
        current = polyline.bbox()
        bbox = current if bbox is None else bbox.union(current)
    return bbox


def transform_for_object(x: float, y: float, scale_x: float, scale_y: float, rotation_deg: float) -> AffineTransform:
    return (
        AffineTransform.translation(x, y)
        .combine(AffineTransform.rotation(rotation_deg))
        .combine(AffineTransform.scale(scale_x, scale_y))
    )


def translate_polylines(polylines: Sequence[Polyline], dx: float, dy: float) -> list[Polyline]:
    translation = AffineTransform.translation(dx, dy)
    return [polyline.transformed(translation) for polyline in polylines]


def scale_polylines(polylines: Sequence[Polyline], sx: float, sy: float | None = None) -> list[Polyline]:
    transform = AffineTransform.scale(sx, sy)
    return [polyline.transformed(transform) for polyline in polylines]


def rotate_polylines(polylines: Sequence[Polyline], degrees: float) -> list[Polyline]:
    transform = AffineTransform.rotation(degrees)
    return [polyline.transformed(transform) for polyline in polylines]


def ensure_nonempty_polyline(polyline: Polyline) -> Polyline | None:
    simplified = polyline.simplified()
    return simplified if simplified.is_valid() else None


def close_polyline_if_needed(polyline: Polyline, tolerance: float = 0.01) -> Polyline:
    if len(polyline.points) < 2:
        return polyline
    if polyline.points[0].distance_to(polyline.points[-1]) > tolerance:
        return Polyline(points=polyline.points + [polyline.points[0]], closed=True)
    return Polyline(points=list(polyline.points), closed=True)
