"""Build a reproducible visual comparison, using a known shaded scene or a photo."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ender_plotter_slicer.raster_importer import (  # noqa: E402
    RasterImportSettings,
    import_raster_file,
    load_raster_image,
)
from ender_plotter_slicer.raster_preview import render_pencil_preview  # noqa: E402


def shaded_scene() -> Image.Image:
    # Analytic diffuse lighting and a soft cast shadow. The known smooth input
    # makes loss of midtones and highlight clipping immediately visible.
    x, y = np.meshgrid(np.linspace(-1.5, 1.5, 800), np.linspace(-1.25, 1.25, 700))
    r2 = (x + .12) ** 2 + (y + .18) ** 2
    z = np.sqrt(np.maximum(0, 1 - r2))
    diffuse = np.clip(-.5 * (x + .12) - .6 * (y + .18) + .62 * z, 0, 1)
    paper = .98 - .60 * np.exp(-((x - .5) / .85) ** 2 - ((y - .86) / .16) ** 2)
    values = np.where(r2 <= 1, .12 + .86 * diffuse, paper)
    return Image.fromarray(np.uint8(np.clip(values, 0, 1) * 255))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Optional source photograph. Default: generated shaded sphere.")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/images/pencil_comparison.png")
    args = parser.parse_args()
    if args.input:
        path = args.input
    else:
        path = ROOT / "examples/pencil_still_life.png"
        shaded_scene().save(path)
    source = load_raster_image(path)
    balanced = RasterImportSettings(width_mm=120, max_height_mm=120)
    modes = [
        ("Legacy · horizontal scanlines", replace(balanced, style="scanline", darkness_threshold=.35,
             tone_layers=3, horizontal_resolution_mm=.35, line_spacing_mm=.45, min_segment_mm=.6,
             merge_gap_mm=.35, contrast=1, auto_contrast=False, smoothing_mm=0)),
        ("Pencil · tonal crosshatching", balanced),
        ("Pencil · form-following", replace(balanced, style="flow", tone_layers=3, stroke_length_mm=14)),
    ]
    panels = [("Source · shaded reference", source)]
    for label, settings in modes:
        result = import_raster_file(path, settings)
        print(result.notes)
        panels.append((label, render_pencil_preview(result.polylines, result.width_mm, result.height_mm,
                                                    settings.pencil_width_mm, settings.stroke_opacity, max_pixels=1200)))
    width, height = 480, 520
    canvas = Image.new("RGB", (width * len(panels), height), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
        small = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()
    for index, (label, panel) in enumerate(panels):
        image = ImageOps.contain(panel, (width - 28, height - 100), Image.Resampling.LANCZOS)
        x = index * width
        draw.text((x + 16, 18), label, fill="#222222", font=font)
        canvas.paste(image, (x + (width - image.width) // 2, 56 + (height - 110 - image.height) // 2))
        if index:
            draw.line((x, 10, x, height - 35), fill="#dddddd")
    draw.text((16, height - 26), "Simulated graphite from actual plot paths. Fixed Z pressure. Paper and pencil affect the physical result.",
              fill="#555555", font=small)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("L").save(args.output, optimize=True)
    print(args.output)


if __name__ == "__main__":
    main()
