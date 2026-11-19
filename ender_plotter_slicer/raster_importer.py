from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from math import ceil, hypot, isfinite
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from .geometry import Point, Polyline


class RasterImportError(RuntimeError):
    pass


class RasterImportCancelled(RasterImportError):
    pass


@dataclass(slots=True)
class RasterImportSettings:
    width_mm: float = 120.0
    max_height_mm: float = 180.0
    horizontal_resolution_mm: float = 0.20
    line_spacing_mm: float = 0.42
    darkness_threshold: float = 0.04
    tone_layers: int = 4
    contrast: float = 1.08
    gamma: float = 1.0
    invert: bool = False
    min_segment_mm: float = 0.45
    merge_gap_mm: float = 0.0
    style: str = "crosshatch"
    hatch_angle_deg: float = 35.0
    pencil_width_mm: float = 0.30
    stroke_opacity: float = 0.65
    auto_contrast: bool = True
    smoothing_mm: float = 0.12
    flow_smoothing_mm: float = 0.8
    stroke_length_mm: float = 18.0
    seed: int = 42


def raster_presets() -> dict[str, RasterImportSettings]:
    """Return fresh settings; editing one import cannot modify another."""
    pencil = RasterImportSettings()
    return {
        "Pencil · balanced": pencil,
        "Pencil · fine portrait": replace(
            pencil, horizontal_resolution_mm=0.14, line_spacing_mm=0.30,
            pencil_width_mm=0.22, tone_layers=5, contrast=1.0, min_segment_mm=0.28,
        ),
        "Pencil · form-following": replace(pencil, style="flow", tone_layers=3, stroke_length_mm=14.0),
        "Pencil · bold contrast": replace(pencil, contrast=1.3, gamma=0.85, tone_layers=5),
        "Line art · legacy scanlines": replace(
            pencil, style="scanline", horizontal_resolution_mm=0.35,
            line_spacing_mm=0.45, darkness_threshold=0.45, tone_layers=1,
            auto_contrast=False, contrast=1.0, smoothing_mm=0.0,
        ),
    }


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
        for left, right in zip(dark_indices[:-1], dark_indices[1:], strict=True):
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


def load_raster_image(path: str | Path) -> Image.Image:
    """Orient the source and composite transparency onto white paper."""
    path = Path(path)
    try:
        with Image.open(path) as raw_image:
            image = ImageOps.exif_transpose(raw_image)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                return Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
            return image.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise RasterImportError(f"Unsupported or damaged image file: {path.name}") from exc
    except (OSError, ValueError) as exc:
        raise RasterImportError(f"Could not read image '{path.name}': {exc}") from exc


def _validate_settings(settings: RasterImportSettings) -> None:
    if settings.style not in {"scanline", "crosshatch", "flow"}:
        raise RasterImportError(f"Unknown drawing style: {settings.style}")
    for item in fields(settings):
        value = getattr(settings, item.name)
        if isinstance(value, (float, int)) and not isfinite(value):
            raise RasterImportError(f"{item.name} must be finite.")
    for name in ("width_mm", "max_height_mm", "contrast", "gamma", "pencil_width_mm", "stroke_length_mm"):
        if getattr(settings, name) <= 0:
            raise RasterImportError(f"{name} must be positive.")
    for name in ("min_segment_mm", "merge_gap_mm", "smoothing_mm", "flow_smoothing_mm"):
        if getattr(settings, name) < 0:
            raise RasterImportError(f"{name} must be non-negative.")
    if settings.horizontal_resolution_mm < 0.05 or settings.line_spacing_mm < 0.05:
        raise RasterImportError("Sample distance and line spacing must be at least 0.05 mm.")
    if not 0 <= settings.darkness_threshold <= 1 or not 0 < settings.stroke_opacity <= 1:
        raise RasterImportError("Threshold must be between 0 and 1; stroke opacity must be between 0 (exclusive) and 1.")
    if not isinstance(settings.tone_layers, int) or not 1 <= settings.tone_layers <= 8:
        raise RasterImportError("Tone layers must be an integer between 1 and 8.")
    if not isinstance(settings.seed, int) or not 0 <= settings.seed < 2**32:
        raise RasterImportError("Seed must be an integer between 0 and 4294967295.")


def import_raster_file(
    path: str | Path, settings: RasterImportSettings,
    progress: Callable[[int, str], None] | None = None, cancel: Callable[[], bool] | None = None,
) -> RasterImportResult:
    from .pencil_hatching import hatch_image

    _validate_settings(settings)

    def check_cancel():
        if cancel and cancel():
            raise RasterImportCancelled("Image conversion cancelled.")

    check_cancel()
    if progress:
        progress(0, "Reading image")
    path = Path(path)
    image = load_raster_image(path).convert("L")
    width_mm, height_mm = _target_size_mm(image.width, image.height, settings)
    x_step = max(0.05, settings.horizontal_resolution_mm)
    y_step = settings.line_spacing_mm if settings.style == "scanline" else x_step
    columns = max(2, ceil(width_mm / x_step) + 1)
    rows = max(2, ceil(height_mm / y_step) + 1)

    if columns > 5000 or rows > 5000 or columns * rows > 4_000_000:
        raise RasterImportError(
            "Raster import would create too many samples. Increase horizontal resolution or line spacing."
        )

    if settings.style == "crosshatch" and hypot(width_mm, height_mm) ** 2 * settings.tone_layers / (
        settings.line_spacing_mm * x_step
    ) > 30_000_000:
        raise RasterImportError("Too many hatch samples. Increase sample distance / spacing or reduce size / layers.")
    sampled = image.resize((columns, rows), Image.Resampling.LANCZOS)
    if settings.auto_contrast:
        sampled = ImageOps.autocontrast(sampled, cutoff=0.5)
    if settings.smoothing_mm > 0:
        sampled = sampled.filter(ImageFilter.GaussianBlur(settings.smoothing_mm * (columns - 1) / width_mm))
    check_cancel()
    if settings.style != "scanline":
        brightness = np.asarray(sampled, dtype=np.float32) / 255.0
        brightness = np.clip((brightness - 0.5) * settings.contrast + 0.5, 0, 1)
        tone = (1.0 - brightness) ** settings.gamma
        if settings.invert:
            tone = 1.0 - tone
        polylines = hatch_image(tone, width_mm, height_mm, settings, progress, check_cancel)
        for polyline in polylines:
            polyline.allow_join = False
        check_cancel()
        if progress:
            progress(100, "Drawing ready")
        return RasterImportResult(
            str(path), path.name, polylines, width_mm, height_mm, columns, rows,
            f"{settings.style}: {len(polylines):,} strokes; {width_mm:.1f} × {height_mm:.1f} mm; "
            f"{columns} × {rows} samples; {settings.tone_layers} tone layers.",
        )
    pixels = sampled.tobytes()

    cell_w = width_mm / columns
    cell_h = height_mm / rows
    tone_layers = max(1, min(8, int(settings.tone_layers)))
    min_threshold = _clip01(settings.darkness_threshold)
    gap_columns = max(0, round(settings.merge_gap_mm / cell_w))
    min_segment_mm = max(0.0, settings.min_segment_mm)

    polylines: list[Polyline] = []
    for row in range(rows):
        check_cancel()
        if progress and row % 20 == 0:
            progress(10 + int(85 * row / rows), "Converting legacy scanlines")
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
                polylines.append(Polyline([Point(x0, y), Point(x1, y)], closed=False, allow_join=False))
        if len(polylines) > 100_000:
            raise RasterImportError("Too many strokes. Increase spacing or reduce size / layers.")

    notes = (
        f"Raster image converted to {len(polylines)} brightness scanline segments. "
        f"Sampled {columns}x{rows}; tone layers={tone_layers}; threshold={min_threshold:.2f}."
    )
    check_cancel()
    if progress:
        progress(100, "Drawing ready")
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
