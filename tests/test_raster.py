from dataclasses import asdict, replace
from math import atan2, isfinite

import numpy as np
import pytest
from PIL import Image

from ender_plotter_slicer.document import PlotterDocument, RasterObject
from ender_plotter_slicer.project_io import load_project, save_project
from ender_plotter_slicer.raster_importer import (
    RasterImportCancelled,
    RasterImportError,
    RasterImportSettings,
    import_raster_file,
    load_raster_image,
)
from ender_plotter_slicer.raster_preview import render_pencil_preview


def source(tmp_path, values, mode=None):
    path = tmp_path / "image.png"
    Image.fromarray(np.array(values, dtype=np.uint8), mode=mode).save(path)
    return path


def settings(**kwargs):
    return replace(RasterImportSettings(width_mm=40, max_height_mm=40, auto_contrast=False,
                                       contrast=1, smoothing_mm=0), **kwargs)


@pytest.mark.parametrize("style", ["crosshatch", "flow", "scanline"])
def test_white_paper_and_transparent_black_stay_empty(tmp_path, style):
    rgba = np.zeros((40, 40, 4), dtype=np.uint8)
    path = source(tmp_path, rgba)
    assert load_raster_image(path).getpixel((10, 10)) == (255, 255, 255)
    assert not import_raster_file(path, settings(style=style)).polylines
    path = source(tmp_path, np.full((40, 40), 255))
    assert not import_raster_file(path, settings(style=style)).polylines


def test_continuous_tones_instead_of_four_brightness_bands(tmp_path):
    # 32 known gray patches, rendered from real paths at measured stroke width.
    pixels = np.tile(np.repeat(np.linspace(255, 0, 32).astype(np.uint8), 30), (240, 1))
    path = source(tmp_path, pixels)
    s = settings(width_mm=160, max_height_mm=40, darkness_threshold=0, tone_layers=6)
    result = import_raster_file(path, s)
    image = np.asarray(render_pencil_preview(result.polylines, result.width_mm, result.height_mm,
                                             s.pencil_width_mm, s.stroke_opacity, max_pixels=1600)) / 255
    means = [1 - image[50:-50, i * 50 + 10:(i + 1) * 50 - 10].mean() for i in range(32)]
    assert min(np.diff(means)) > -0.015, means
    assert len(set(round(x, 2) for x in means)) >= 27, means
    assert np.mean(np.abs(np.array(means) - np.linspace(0, 1, 32))) < 0.09
    assert means[-1] > 0.90
    assert means[0] == 0


def test_dark_shadows_receive_multiple_directions(tmp_path):
    result = import_raster_file(source(tmp_path, np.zeros((40, 40))), settings(tone_layers=4))
    angles = {round(atan2(p.points[-1].y - p.points[0].y, p.points[-1].x - p.points[0].x) % np.pi, 3)
              for p in result.polylines}
    assert len(angles) == 4
    assert all(not p.allow_join for p in result.polylines)


@pytest.mark.parametrize("style", ["crosshatch", "flow"])
def test_highlight_hole_is_not_bridged_even_with_large_merge_setting(tmp_path, style):
    pixels = np.zeros((200, 200), dtype=np.uint8)
    pixels[65:135, 65:135] = 255
    result = import_raster_file(source(tmp_path, pixels), settings(style=style, merge_gap_mm=10))
    assert result.polylines
    for line in result.polylines:
        for a, b in zip(line.points[:-1], line.points[1:], strict=True):
            # Test the interior of every segment, not just its endpoints.
            for t in np.linspace(0, 1, 30):
                x, y = a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t
                assert not (14.2 < x < 25.8 and 14.2 < y < 25.8)


def test_flow_strokes_curve_and_remain_reproducible(tmp_path):
    y, x = np.mgrid[-1:1:160j, -1:1:160j]
    pixels = np.uint8((1 - np.clip(0.9 * (1 - x * x - y * y), 0, 1)) * 255)
    path = source(tmp_path, pixels)
    s = settings(style="flow", tone_layers=1, flow_smoothing_mm=1.2)
    a, b = import_raster_file(path, s), import_raster_file(path, s)
    assert [p.as_serializable() for p in a.polylines] == [p.as_serializable() for p in b.polylines]
    assert sum(len(p.points) > 3 for p in a.polylines) > 10
    for line in a.polylines:
        for p in line.points:
            assert isfinite(p.x) and isfinite(p.y)
            assert 0 <= p.x <= a.width_mm and 0 <= p.y <= a.height_mm


def test_exif_orientation_and_aspect_ratio(tmp_path):
    path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (40, 80), "gray")
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    assert load_raster_image(path).size == (80, 40)
    result = import_raster_file(path, settings(width_mm=60, max_height_mm=40))
    assert (result.width_mm, result.height_mm) == (60, 30)


@pytest.mark.parametrize("style", ["crosshatch", "flow", "scanline"])
def test_conversion_can_be_cancelled_without_returning_partial_paths(tmp_path, style):
    path = source(tmp_path, np.zeros((80, 80)))
    updates = []
    def progress(percent, text):
        updates.append(percent)
    with pytest.raises(RasterImportCancelled):
        import_raster_file(path, settings(style=style), progress, lambda: len(updates) >= 3)


@pytest.mark.parametrize("kwargs", [{"gamma": 0}, {"contrast": float("nan")}, {"line_spacing_mm": 0},
                                    {"tone_layers": 99}, {"darkness_threshold": -0.1}, {"stroke_opacity": 2},
                                    {"seed": -1}, {"style": "unknown"}])
def test_invalid_settings_are_rejected(tmp_path, kwargs):
    with pytest.raises(RasterImportError):
        import_raster_file(source(tmp_path, np.zeros((10, 10))), settings(**kwargs))


def test_pathological_detail_is_rejected_before_hatching(tmp_path):
    with pytest.raises(RasterImportError, match="[Tt]oo many"):
        import_raster_file(source(tmp_path, np.zeros((10, 10))), settings(
            width_mm=400, max_height_mm=400, line_spacing_mm=.05, horizontal_resolution_mm=.05, tone_layers=8))


def test_project_keeps_settings_and_paths_without_the_source_image(tmp_path):
    path = source(tmp_path, np.zeros((40, 40)))
    s = settings(style="flow", tone_layers=2)
    raster = import_raster_file(path, s)
    doc = PlotterDocument(objects=[RasterObject(local_polylines=raster.polylines, raster_settings=asdict(s), source_path=str(path))])
    project = tmp_path / "drawing.plotproj.json"
    save_project(doc, project)
    path.unlink()
    restored = load_project(project)
    assert restored.to_dict() == doc.to_dict()
    assert restored.objects[0].local_polylines
    # Old project files did not store allow_join or raster_settings.
    data = doc.to_dict()
    del data["objects"][0]["raster_settings"]
    for line in data["objects"][0]["local_polylines"]:
        del line["allow_join"]
    old = PlotterDocument.from_dict(data)
    assert all(not line.allow_join for line in old.objects[0].local_polylines)
