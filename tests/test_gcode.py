from random import Random

import pytest

from ender_plotter_slicer.document import DocumentObject, PlotterDocument, RasterObject
from ender_plotter_slicer.gcode import generate_gcode
from ender_plotter_slicer.geometry import Point, Polyline
from ender_plotter_slicer.path_order import optimise_order


def test_pencil_paths_lift_across_small_highlights():
    doc = PlotterDocument()
    doc.profile.origin_mode = "bottom_left"
    doc.profile.work_offset_x_mm = doc.profile.work_offset_y_mm = 0
    doc.gcode.join_tolerance_mm = 2
    doc.gcode.optimize_order = False
    doc.objects = [RasterObject(local_polylines=[
        Polyline([Point(10, 10), Point(20, 10)], allow_join=False),
        Polyline([Point(20.1, 10), Point(30, 10)], allow_join=False),
    ])]
    result = generate_gcode(doc)
    assert result.gcode.count("; pen down") == 2
    assert result.stats.draw_length_mm == pytest.approx(19.9)
    assert not any(seg.is_draw and seg.start == Point(20, 10) and seg.end == Point(20.1, 10)
                   for seg in result.preview.segments)
    assert not any(" E" in line for line in result.lines if line.startswith(("G0 ", "G1 ")))
    zs = {float(line.split('Z')[1].split()[0]) for line in result.lines if line.startswith('G1 Z')}
    assert zs <= {doc.profile.pen_down_z_mm, doc.profile.pen_up_z_mm, doc.profile.retract_z_mm}


def test_first_path_near_parking_position_still_moves_to_its_start():
    doc = PlotterDocument()
    doc.profile.origin_mode = "bottom_left"
    doc.profile.work_offset_x_mm = doc.profile.work_offset_y_mm = 0
    doc.profile.safe_start_x_mm = doc.profile.safe_start_y_mm = 10
    doc.objects = [DocumentObject(local_polylines=[Polyline([Point(10.1, 10), Point(20, 10)])])]
    result = generate_gcode(doc)
    draws = [s for s in result.preview.segments if s.is_draw]
    assert draws[0].start == Point(10.1, 10)


def test_closed_paths_are_closed_in_gcode_and_short_endpoints_survive():
    doc = PlotterDocument()
    doc.objects = [DocumentObject(local_polylines=[Polyline([Point(1, 1), Point(10, 1), Point(10, 10)], closed=True)])]
    result = generate_gcode(doc)
    assert result.stats.draw_length_mm == pytest.approx(18 + 2**.5 * 9)
    line = Polyline([Point(0, 0), Point(1, 0), Point(1.01, .01)])
    assert line.simplified(.1).points[-1] == line.points[-1]


def brute_order(paths):
    remaining = list(enumerate(paths))[1:]
    result = [paths[0]]
    while remaining:
        current = result[-1].points[-1]
        choices = [(current.distance_to(p.points[-1] if reverse else p.points[0]) ** 2, index, reverse, p)
                   for index, p in remaining for reverse in (False, True)]
        _, index, reverse, path = min(choices, key=lambda v: v[:3])
        result.append(path.reversed() if reverse else path)
        remaining = [(i, p) for i, p in remaining if i != index]
    return result


def test_scalable_ordering_matches_exact_nearest_endpoint_search():
    rng = Random(42)
    paths = [Polyline([Point(rng.random() * 100, rng.random() * 100),
                       Point(rng.random() * 100, rng.random() * 100)], allow_join=False) for _ in range(350)]
    assert [p.as_serializable() for p in optimise_order(paths)] == [p.as_serializable() for p in brute_order(paths)]
    assert optimise_order([]) == []
    # Coincident endpoints must not discard paths or make tie order unstable.
    ties = [Polyline([Point(0, 0), Point(1, 0)]) for _ in range(50)]
    assert len(optimise_order(ties)) == len(ties)


def test_pen_up_travel_is_optional_and_reduces_lift_time():
    doc = PlotterDocument(objects=[RasterObject(local_polylines=[
        Polyline([Point(10, 10), Point(20, 10)], allow_join=False),
        Polyline([Point(20, 11), Point(10, 11)], allow_join=False),
    ])])
    full = generate_gcode(doc)
    doc.gcode.retract_between_paths = False
    short = generate_gcode(doc)
    assert full.stats.draw_length_mm == short.stats.draw_length_mm
    assert full.stats.travel_length_mm == short.stats.travel_length_mm
    assert short.stats.z_length_mm < full.stats.z_length_mm
    assert short.stats.motion_time_lower_bound_s < full.stats.motion_time_lower_bound_s
    assert short.gcode.count("; initial retract") == 1
    assert "; retract" in short.gcode
    # Every between-stroke XY travel has the pencil at least at Pen-up Z.
    z = float('inf')
    for line in short.lines:
        if line.startswith('G1 Z'):
            z = float(line.split('Z')[1].split()[0])
        if line.startswith('G0 X'):
            assert z >= doc.profile.pen_up_z_mm
    assert short.stats.motion_time_lower_bound_s > short.stats.draw_length_mm / doc.profile.plot_feed_mm_min * 60


@pytest.mark.parametrize('feed', [0, -100, float('nan')])
def test_invalid_feed_does_not_produce_unusable_gcode(feed):
    doc = PlotterDocument()
    doc.profile.plot_feed_mm_min = feed
    with pytest.raises(ValueError, match='positive'):
        generate_gcode(doc)


def test_existing_svg_example_still_exports_all_geometry():
    from pathlib import Path

    from ender_plotter_slicer.svg_importer import import_svg_file

    artwork = import_svg_file(Path(__file__).resolve().parents[1] / 'examples/sample_line_art.svg')
    assert len(artwork.polylines) == 3
    doc = PlotterDocument(objects=[DocumentObject(local_polylines=artwork.polylines)])
    result = generate_gcode(doc)
    assert result.stats.path_count == 3
    assert result.stats.draw_length_mm == pytest.approx(sum(p.length() for p in artwork.polylines), rel=.005)
