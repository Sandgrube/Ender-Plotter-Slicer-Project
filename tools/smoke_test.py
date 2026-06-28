from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ender_plotter_slicer.document import DocumentObject, PlotterDocument
from ender_plotter_slicer.gcode import generate_gcode
from ender_plotter_slicer.geometry import Point, Polyline
from ender_plotter_slicer.raster_importer import RasterImportSettings, import_raster_file



def main() -> int:
    image_path = ROOT / "examples" / "sample_raster.png"
    raster = import_raster_file(
        image_path,
        RasterImportSettings(width_mm=60.0, max_height_mm=60.0, horizontal_resolution_mm=1.0, line_spacing_mm=1.0),
    )
    assert raster.polylines, "Raster import generated no polylines."

    doc = PlotterDocument(project_name="Smoke Test")
    obj = DocumentObject(
        name="Smoke Test Square",
        local_polylines=[Polyline([Point(0, 0), Point(20, 0), Point(20, 20), Point(0, 20), Point(0, 0)])],
        x_mm=20.0,
        y_mm=20.0,
    )
    doc.add_object(obj)
    result = generate_gcode(doc)
    assert "G21" in result.gcode
    assert "G90" in result.gcode
    assert result.stats.draw_length_mm > 0
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
