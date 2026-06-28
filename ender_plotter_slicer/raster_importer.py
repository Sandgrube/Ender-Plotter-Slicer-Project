from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .geometry import Point, Polyline


class RasterImportError(RuntimeError):
    pass


@dataclass(slots=True)
class RasterImportSettings:
    width_mm: float = 120.0
    max_height_mm: float = 180.0
    horizontal_resolution_mm: float = 0.35
    line_spacing_mm: float = 0.45
    darkness_threshold: float = 0.35
    tone_layers: int = 3
    contrast: float = 1.0
    gamma: float = 1.0
    invert: bool = False
    min_segment_mm: float = 0.60
    merge_gap_mm: float = 0.35


@dataclass(slots=True)
class RasterImportResult:
    source_path: str
    source_name: str
    polylines: list[Polyline]
    width_mm: float
    height_mm: float
    sampled_columns: int
    sampled_rows: int
    notes: str


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _pixel_darkness(pixel_value: int, settings: RasterImportSettings) -> float:
    # pixel_value: 0 = black, 255 = white.
    brightness = pixel_value / 255.0
    brightness = _clip01((brightness - 0.5) * settings.contrast + 0.5)
    darkness = 1.0 - brightness
    if settings.gamma > 0.001 and settings.gamma != 1.0:
        darkness = darkness ** settings.gamma
    if settings.invert:
        darkness = 1.0 - darkness
    return _clip01(darkness)


def _target_size_mm(image_width: int, image_height: int, settings: RasterImportSettings) -> tuple[float, float]:
    if image_width <= 0 or image_height <= 0:
        raise RasterImportError("Invalid image dimensions.")
    width_mm = max(1.0, settings.width_mm)
    height_mm = width_mm * (image_height / image_width)
    max_height = max(1.0, settings.max_height_mm)
    if height_mm > max_height:
        scale = max_height / height_mm
        width_mm *= scale
        height_mm = max_height
    return width_mm, height_mm


def _make_runs(dark_values: list[float], threshold: float, gap_columns: int) -> list[tuple[int, int]]:
    flags = [value >= threshold for value in dark_values]
    if gap_columns > 0:
        dark_indices = [idx for idx, flag in enumerate(flags) if flag]
        for left, right in zip(dark_indices[:-1], dark_indices[1:]):
            gap = right - left - 1
            if 0 < gap <= gap_columns:
                for idx in range(left + 1, right):
                    flags[idx] = True

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for idx, is_dark in enumerate(flags):
        if is_dark and start is None:
            start = idx
        elif not is_dark and start is not None:
            runs.append((start, idx - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def import_raster_file(path: str | Path, settings: RasterImportSettings) -> RasterImportResult:
    path = Path(path)
    if not path.exists():
        raise RasterImportError(f"Image file does not exist: {path}")

    try:
        with Image.open(path) as raw_image:
            image = ImageOps.exif_transpose(raw_image).convert("L")
    except UnidentifiedImageError as exc:
        raise RasterImportError(f"Unsupported or damaged image file: {path.name}") from exc
    except Exception as exc:
        raise RasterImportError(f"Could not read image '{path.name}': {exc}") from exc

    width_mm, height_mm = _target_size_mm(image.width, image.height, settings)
    x_step = max(0.05, settings.horizontal_resolution_mm)
    y_step = max(0.05, settings.line_spacing_mm)
    columns = max(2, round(width_mm / x_step))
    rows = max(2, round(height_mm / y_step))

    if columns > 3500 or rows > 3500:
        raise RasterImportError(
            "Raster import would create too many samples. Increase horizontal resolution or line spacing."
        )

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:  # pragma: no cover - fallback for old Pillow
        resample = Image.LANCZOS
    sampled = image.resize((columns, rows), resample)
    pixels = sampled.tobytes()

    cell_w = width_mm / columns
    cell_h = height_mm / rows
    tone_layers = max(1, min(8, int(settings.tone_layers)))
    min_threshold = _clip01(settings.darkness_threshold)
    gap_columns = max(0, round(settings.merge_gap_mm / cell_w))
    min_segment_mm = max(0.0, settings.min_segment_mm)

    polylines: list[Polyline] = []
    for row in range(rows):
        offset = row * columns
        dark_values = [_pixel_darkness(value, settings) for value in pixels[offset : offset + columns]]
        base_y = row * cell_h

        for layer in range(tone_layers):
            if tone_layers == 1:
                threshold = min_threshold
                y = base_y + cell_h * 0.5
            else:
                threshold = min_threshold + (1.0 - min_threshold) * (layer / tone_layers)
                y = base_y + cell_h * ((layer + 0.5) / tone_layers)
            threshold = _clip01(threshold)

            for start_col, end_col in _make_runs(dark_values, threshold, gap_columns):
                x0 = start_col * cell_w
                x1 = (end_col + 1) * cell_w
                if x1 - x0 < min_segment_mm:
                    continue
                polylines.append(Polyline([Point(x0, y), Point(x1, y)], closed=False))

    notes = (
        f"Raster image converted to {len(polylines)} brightness scanline segments. "
        f"Sampled {columns}x{rows}; tone layers={tone_layers}; threshold={min_threshold:.2f}."
    )
    return RasterImportResult(
        source_path=str(path),
        source_name=path.name,
        polylines=polylines,
        width_mm=width_mm,
        height_mm=height_mm,
        sampled_columns=columns,
        sampled_rows=rows,
        notes=notes,
    )
