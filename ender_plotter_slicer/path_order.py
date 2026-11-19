"""Exact nearest-endpoint ordering with a deletable, balanced k-d tree."""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import Point, Polyline


@dataclass(slots=True)
class _Node:
    x: float
    y: float
    path_index: int
    reverse: bool
    axis: int
    count: int
    parent: _Node | None = None
    left: _Node | None = None
    right: _Node | None = None


class _EndpointIndex:
    def __init__(self, paths: list[Polyline]):
        self.active = [True] * len(paths)
        self.endpoints: list[list[_Node]] = [[] for _ in paths]
        items = [(point.x, point.y, index, reverse) for index, path in enumerate(paths)
                 for point, reverse in ((path.points[0], False), (path.points[-1], True))]
        self.root = self._build(items, 0)

    def _build(self, items, axis, parent=None):
        if not items:
            return None
        items.sort(key=lambda item: (item[axis], item[2], item[3]))
        middle = len(items) // 2
        x, y, index, reverse = items[middle]
        node = _Node(x, y, index, reverse, axis, len(items), parent)
        self.endpoints[index].append(node)
        node.left = self._build(items[:middle], 1 - axis, node)
        node.right = self._build(items[middle + 1:], 1 - axis, node)
        return node

    def remove(self, index):
        self.active[index] = False
        for endpoint in self.endpoints[index]:
            node = endpoint
            while node is not None:
                node.count -= 1
                node = node.parent

    def nearest(self, point: Point) -> tuple[int, bool]:
        best = (float("inf"), len(self.active), False)

        def visit(node):
            nonlocal best
            if node is None or node.count == 0:
                return
            dx, dy = node.x - point.x, node.y - point.y
            if self.active[node.path_index]:
                candidate = (dx * dx + dy * dy, node.path_index, node.reverse)
                if candidate < best:
                    best = candidate
            delta = dx if node.axis == 0 else dy
            near, far = (node.left, node.right) if delta > 0 else (node.right, node.left)
            visit(near)
            if delta * delta <= best[0]:
                visit(far)

        visit(self.root)
        return best[1], best[2]


def optimise_order(polylines: list[Polyline]) -> list[Polyline]:
    if not polylines:
        return []
    index = _EndpointIndex(polylines)
    ordered = [polylines[0]]
    index.remove(0)
    while len(ordered) < len(polylines):
        path_index, reverse = index.nearest(ordered[-1].points[-1])
        path = polylines[path_index]
        ordered.append(path.reversed() if reverse else path)
        index.remove(path_index)
    return ordered
