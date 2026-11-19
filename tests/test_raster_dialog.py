from time import monotonic, sleep

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from ender_plotter_slicer.gui.raster_dialog import RasterImportDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate, timeout=20):
    deadline = monotonic() + timeout
    while not predicate():
        app.processEvents()
        # QTest.qWait can hold the GIL while a Python QThread needs to run.
        sleep(.01)
        assert monotonic() < deadline, "Raster worker did not finish"
    app.processEvents()


def test_preview_is_the_imported_geometry_and_edits_invalidate_it(app, tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (80, 80), "gray").save(path)
    dialog = RasterImportDialog(str(path))
    dialog.controls["width_mm"].setValue(35)
    dialog.controls["max_height_mm"].setValue(35)
    dialog.show()
    app.processEvents()
    wait_for(app, lambda: dialog._worker is None and dialog.result is not None)
    assert dialog.import_button.isEnabled()
    assert dialog.result.polylines
    assert dialog.settings_dict["width_mm"] == 35
    dialog.controls["gamma"].setValue(1.4)
    assert dialog.result is None
    assert not dialog.import_button.isEnabled()
    dialog.build_preview()
    wait_for(app, lambda: dialog._worker is None)
    assert dialog.result is not None
    dialog.accept()
    assert dialog.result is not None


def test_cancel_waits_for_worker_before_destroying_dialog(app, tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (80, 80), "black").save(path)
    dialog = RasterImportDialog(str(path))
    dialog.show()
    app.processEvents()
    assert dialog._worker is not None
    dialog.reject()
    wait_for(app, lambda: dialog._worker is None)
    assert not dialog.isVisible()


def test_machine_preview_is_upright_and_fits_after_resize(app):
    from PySide6.QtCore import QPointF

    from ender_plotter_slicer.document import DocumentObject, PlotterDocument
    from ender_plotter_slicer.gcode import generate_gcode
    from ender_plotter_slicer.geometry import Point, Polyline
    from ender_plotter_slicer.gui.dialogs import PreviewDialog

    doc = PlotterDocument(objects=[DocumentObject(local_polylines=[Polyline([Point(10, 10), Point(190, 190)])])])
    dialog = PreviewDialog(doc, generate_gcode(doc), [])
    dialog.show()
    for width, height in ((1200, 760), (950, 650)):
        dialog.resize(width, height)
        app.processEvents()
        assert dialog.view.transform().m22() < 0
        profile = doc.profile
        for x, y in ((profile.work_offset_x_mm, profile.work_offset_y_mm),
                     (profile.work_offset_x_mm + profile.work_area_width_mm,
                      profile.work_offset_y_mm + profile.work_area_height_mm)):
            point = dialog.view.mapFromScene(QPointF(x, y))
            assert dialog.view.viewport().rect().contains(point)
    dialog.reject()
