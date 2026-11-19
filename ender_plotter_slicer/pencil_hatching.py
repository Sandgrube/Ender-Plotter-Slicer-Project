"""Continuous-tone pencil paths. No Qt, edge-only tracing, or Z-pressure modulation."""
from __future__ import annotations

from math import atan2, ceil, cos, hypot, log1p, pi, sin
from typing import TYPE_CHECKING

import numpy as np

from .geometry import Point, Polyline

if TYPE_CHECKING:
    from .raster_importer import RasterImportSettings


def _sample(field, x, y, width, height):
    fx = np.clip(np.asarray(x) * (field.shape[1] - 1) / width, 0, field.shape[1] - 1)
    fy = np.clip(np.asarray(y) * (field.shape[0] - 1) / height, 0, field.shape[0] - 1)
    ix = np.minimum(fx.astype(int), field.shape[1] - 2)
    iy = np.minimum(fy.astype(int), field.shape[0] - 2)
    tx, ty = fx - ix, fy - iy
    return ((field[iy, ix] * (1 - tx) + field[iy, ix + 1] * tx) * (1 - ty)
            + (field[iy + 1, ix] * (1 - tx) + field[iy + 1, ix + 1] * tx) * ty)


def _scalar(field, x, y, width, height):
    # Avoid NumPy temporaries inside the streamline integrator.
    fx = min(field.shape[1] - 1., max(0., x * (field.shape[1] - 1) / width))
    fy = min(field.shape[0] - 1., max(0., y * (field.shape[0] - 1) / height))
    ix, iy = min(int(fx), field.shape[1] - 2), min(int(fy), field.shape[0] - 2)
    tx, ty = fx - ix, fy - iy
    return float((field[iy, ix] * (1 - tx) + field[iy, ix + 1] * tx) * (1 - ty)
                 + (field[iy + 1, ix] * (1 - tx) + field[iy + 1, ix + 1] * tx) * ty)


def _check_paths(paths):
    from .raster_importer import RasterImportError
    if len(paths) > 100_000:
        raise RasterImportError("Too many strokes. Increase line spacing or reduce image size / tone layers.")


def _line_interval(offset, dx, dy, width, height):
    # p(t) = offset * normal + t * direction; intersect with the paper rectangle.
    x0, y0 = -dy * offset, dx * offset
    lo, hi = -float("inf"), float("inf")
    for start, direction, limit in ((x0, dx, width), (y0, dy, height)):
        if abs(direction) < 1e-10:
            if not 0 <= start <= limit:
                return None
        else:
            a, b = -start / direction, (limit - start) / direction
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    return (lo, hi) if hi > lo else None


def _crosshatch(exposure, width, height, settings, progress, check_cancel):
    offsets = (0, 90, 45, 135, 22.5, 112.5, 67.5, 157.5)
    paths = []
    for layer in range(settings.tone_layers):
        coverage = np.clip(exposure - layer, 0, 1)
        if not np.any(coverage > 0):
            break
        angle = (settings.hatch_angle_deg + offsets[layer]) * pi / 180
        dx, dy = cos(angle), sin(angle)
        projections = (0, -dy * width, dx * height, -dy * width + dx * height)
        low, high = min(projections), max(projections)
        count = max(1, ceil((high - low) / settings.line_spacing_mm))
        for row in range(count):
            if row % 16 == 0:
                check_cancel()
                if progress:
                    progress(10 + int(85 * (layer + row / count) / settings.tone_layers), "Building tonal crosshatching")
            offset = low + (row + 0.5) * settings.line_spacing_mm
            interval = _line_interval(offset, dx, dy, width, height)
            if interval is None:
                continue
            lo, hi = interval
            steps = max(2, ceil((hi - lo) / settings.horizontal_resolution_mm) + 1)
            t = np.linspace(lo, hi, steps)
            values = _sample(coverage, -dy * offset + t * dx, dx * offset + t * dy, width, height)
            # Low-discrepancy ranks select entire strokes at continuously varying
            # density. Per-pixel random dithering would fragment them into dots.
            rank = 0.005 + 0.99 * ((0.5 + row * 0.618033988749895 + layer * 0.38196601125) % 1)
            active = values > rank
            changes = np.diff(np.r_[False, active, False].astype(np.int8))
            for start, end in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1), strict=True):
                a, b = t[start], t[end - 1]
                if start > 0:
                    a = np.interp(rank, [values[start - 1], values[start]], [t[start - 1], t[start]])
                if end < steps:
                    b = np.interp(rank, [values[end], values[end - 1]], [t[end], t[end - 1]])
                if b - a < settings.min_segment_mm:
                    continue
                points = [Point(min(width, max(0., -dy * offset + v * dx)),
                                min(height, max(0., dx * offset + v * dy))) for v in (a, b)]
                paths.append(Polyline(points if row % 2 == 0 else points[::-1]))
            _check_paths(paths)
    return paths


def _box_blur(array, radius):
    result = array
    for axis in (0, 1):
        padding = [(0, 0), (0, 0)]
        padding[axis] = (radius + 1, radius)
        summed = np.cumsum(np.pad(result, padding, mode="edge"), axis=axis, dtype=np.float64)
        size = 2 * radius + 1
        result = ((summed[size:] - summed[:-size]) / size if axis == 0
                  else (summed[:, size:] - summed[:, :-size]) / size)
    return result.astype(np.float32)


def _flow_field(tone, width, height, settings):
    gy, gx = np.gradient(tone, height / (tone.shape[0] - 1), width / (tone.shape[1] - 1))
    radius = min(128, max(1, round(settings.flow_smoothing_mm * (tone.shape[1] - 1) / width)))
    xx, yy, xy = (_box_blur(a, radius) for a in (gx * gx, gy * gy, gx * gy))
    strength = np.hypot(xx - yy, 2 * xy)
    coherence = strength / (xx + yy + 1e-8)
    base = 2 * settings.hatch_angle_deg * pi / 180
    weight = np.clip(coherence * 1.4, 0, 1) * np.clip(strength / 0.006, 0, 1)
    # Doubled angles avoid a seam at equivalent directions 0/pi. Coherence
    # blends a preferred direction into flat regions instead of tracing noise.
    return (-weight * (xx - yy) / (strength + 1e-8) + (1 - weight) * cos(base),
            -weight * 2 * xy / (strength + 1e-8) + (1 - weight) * sin(base))


class _StrokeGrid:
    def __init__(self, spacing):
        self.cell = spacing * 2
        self.buckets: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def near(self, x, y, distance):
        ix, iy = int(x // self.cell), int(y // self.cell)
        reach = ceil(distance / self.cell)
        squared = distance * distance
        for cy in range(iy - reach, iy + reach + 1):
            for cx in range(ix - reach, ix + reach + 1):
                for px, py in self.buckets.get((cx, cy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < squared:
                        return True
        return False

    def add(self, points):
        for x, y in points:
            self.buckets.setdefault((int(x // self.cell), int(y // self.cell)), []).append((x, y))


def _compress_curve(points, tolerance=0.025):
    if len(points) < 3:
        return points
    first, last = np.array(points[0]), np.array(points[-1])
    data, delta = np.array(points), last - first
    length = hypot(*delta)
    distances = (np.hypot(*(data - first).T) if length < 1e-10 else
                 np.abs(delta[0] * (data[:, 1] - first[1]) - delta[1] * (data[:, 0] - first[0])) / length)
    index = int(np.argmax(distances))
    if distances[index] <= tolerance:
        return [points[0], points[-1]]
    return _compress_curve(points[:index + 1], tolerance)[:-1] + _compress_curve(points[index:], tolerance)


def _flow_hatch(tone, exposure, width, height, settings, progress, check_cancel):
    from .raster_importer import RasterImportError

    ux, uy = _flow_field(tone, width, height, settings)
    spacing = settings.line_spacing_mm
    step = min(settings.horizontal_resolution_mm, spacing * 0.5)
    columns, rows = ceil(width / spacing), ceil(height / spacing)
    if columns * rows > 350_000:
        raise RasterImportError("Too many flow seeds. Increase line spacing or reduce image size.")
    rng = np.random.default_rng(settings.seed)
    paths, total_steps = [], 0
    for layer in range(settings.tone_layers):
        coverage = np.clip(exposure - layer, 0, 1)
        if not np.any(coverage > 0):
            break
        grid = _StrokeGrid(spacing)
        seeds = rng.permutation(columns * rows)
        rotation = (0, pi / 2, pi / 4, 3 * pi / 4)[layer % 4]

        def value(x, y, coverage=coverage):
            return _scalar(coverage, x, y, width, height)

        def direction(x, y, previous, rotation=rotation):
            angle = 0.5 * atan2(_scalar(uy, x, y, width, height), _scalar(ux, x, y, width, height)) + rotation
            dx, dy = cos(angle), sin(angle)
            return (-dx, -dy) if dx * previous[0] + dy * previous[1] < 0 else (dx, dy)

        def trace(x, y, sign, grid=grid):
            nonlocal total_steps
            points = []
            previous = direction(x, y, (1, 0))
            previous = (previous[0] * sign, previous[1] * sign)
            for _ in range(ceil(settings.stroke_length_mm / (2 * step))):
                total_steps += 1
                if total_steps % 256 == 0:
                    check_cancel()
                if total_steps > 1_500_000:
                    raise RasterImportError("Flow drawing is too detailed. Increase sample distance / spacing or reduce size.")
                dx, dy = direction(x, y, previous)
                # Midpoint integration bends along local image structure.
                dx, dy = direction(x + dx * step / 2, y + dy * step / 2, (dx, dy))
                nx, ny = x + dx * step, y + dy * step
                if not (0 <= nx <= width and 0 <= ny <= height):
                    break
                density = value(nx, ny)
                if density <= 0.01 or grid.near(nx, ny, spacing * 0.85 / max(0.12, density)):
                    break
                if len(points) > 8 and hypot(nx - points[0][0], ny - points[0][1]) < step:
                    break
                points.append((nx, ny))
                x, y, previous = nx, ny, (dx, dy)
            return points

        for index, seed in enumerate(seeds):
            if index % 128 == 0:
                check_cancel()
                if progress:
                    progress(10 + int(85 * (layer + index / len(seeds)) / settings.tone_layers), "Tracing form-following strokes")
            x = (int(seed) % columns + rng.uniform(0.15, 0.85)) * width / columns
            y = (int(seed) // columns + rng.uniform(0.15, 0.85)) * height / rows
            density = value(x, y)
            if density <= 0.01 or grid.near(x, y, spacing * 0.85 / max(0.12, density)):
                continue
            points = trace(x, y, -1)[::-1] + [(x, y)] + trace(x, y, 1)
            length = sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points[:-1], points[1:], strict=True))
            if length >= settings.min_segment_mm and len(points) >= 2:
                grid.add(points[::max(1, int(spacing / (2 * step)))])
                paths.append(Polyline([Point(*p) for p in _compress_curve(points)]))
                _check_paths(paths)
    return paths


def hatch_image(tone, width, height, settings: RasterImportSettings, progress, check_cancel):
    # Convert graphite coverage to optical density. Each additional direction
    # supplies another translucent layer. This is a preview/calibration model,
    # never a command to press the pencil further into the bed.
    normalized = np.clip((tone - settings.darkness_threshold) / max(1e-6, 1 - settings.darkness_threshold), 0, 0.995)
    capacity = min(0.92, settings.pencil_width_mm / settings.line_spacing_mm * settings.stroke_opacity)
    exposure = -np.log1p(-normalized) / -log1p(-capacity)
    check_cancel()
    if settings.style == "flow":
        return _flow_hatch(tone, exposure, width, height, settings, progress, check_cancel)
    return _crosshatch(exposure, width, height, settings, progress, check_cancel)
