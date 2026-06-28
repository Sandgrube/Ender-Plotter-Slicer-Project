from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Point


@dataclass(slots=True)
class PreviewSegment:
    start: Point
    end: Point
    is_draw: bool


@dataclass(slots=True)
class PreviewBundle:
    segments: list[PreviewSegment] = field(default_factory=list)

    @property
    def draw_count(self) -> int:
        return sum(1 for segment in self.segments if segment.is_draw)

    @property
    def travel_count(self) -> int:
        return sum(1 for segment in self.segments if not segment.is_draw)
