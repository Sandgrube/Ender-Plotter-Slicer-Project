from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from ..config import APP_NAME, DEFAULT_PROJECT_EXTENSION, IMAGE_FILE_FILTER, PROJECT_FILE_FILTER, SVG_FILE_FILTER
from ..document import PlotterDocument, RasterObject, TextObject
from ..gcode import generate_gcode
from ..profiles import builtin_profiles
from ..project_io import ProjectIOError, load_project, save_project
from ..svg_importer import SVGImportError, import_svg_file
from ..raster_importer import RasterImportError, import_raster_file
from ..validator import validate_document
from .canvas import CanvasView
from .dialogs import NewTextDialog, PreviewDialog, RasterImportDialog
from .property_panel import PropertyPanel
from .settings_panel import SettingsPanel


class DocumentHistory:
    def __init__(self) -> None:
        self.snapshots: list[dict] = []
        self.index: int = -1

    def reset(self, document: PlotterDocument) -> None:
        self.snapshots = [document.to_dict()]
        self.index = 0

    def push(self, document: PlotterDocument) -> None:
        snapshot = document.to_dict()
        if self.index >= 0 and snapshot == self.snapshots[self.index]:
            return
        self.snapshots = self.snapshots[: self.index + 1]
        self.snapshots.append(snapshot)
        self.index = len(self.snapshots) - 1

    def can_undo(self) -> bool:
        return self.index > 0

    def can_redo(self) -> bool:
        return self.index >= 0 and self.index < len(self.snapshots) - 1

    def undo(self) -> dict | None:
        if not self.can_undo():
            return None
        self.index -= 1
        return copy.deepcopy(self.snapshots[self.index])

    def redo(self) -> dict | None:
        if not self.can_redo():
            return None
        self.index += 1
        return copy.deepcopy(self.snapshots[self.index])


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.profile_registry = builtin_profiles()
        self.document = PlotterDocument()
        self.document.profile = copy.deepcopy(self.profile_registry["ELEGOO Neptune 2 Pen Plotter"])
        self.history = DocumentHistory()
        self.history.reset(self.document)
        self.modified = False
        self._suspend_history = False

        self.setWindowTitle(APP_NAME)
        self.resize(1480, 920)

        self.canvas = CanvasView(self.document, self)
        self.setCentralWidget(self.canvas)

        self.property_panel = PropertyPanel(self)
        self.property_panel.propertiesApplied.connect(self.apply_object_properties)

        self.settings_panel = SettingsPanel(self.profile_registry, self)
        self.settings_panel.load_from_document(self.document)
        self.settings_panel.settingsApplied.connect(self.apply_document_settings)

        self._create_docks()
        self._create_actions()
        self._create_menus_and_toolbar()

        status = QStatusBar()
        self.setStatusBar(status)
        self.selection_display = QLabel("Selection: 0")
        self.zoom_display = QLabel("Zoom: 100%")
        self.coord_display = QLabel("X: 0.0 mm   Y: 0.0 mm")
        status.addPermanentWidget(self.selection_display)
        status.addPermanentWidget(self.zoom_display)
        status.addPermanentWidget(self.coord_display)

        self.canvas.coordinateChanged.connect(self.on_canvas_coordinate_changed)
        self.canvas.selectionChangedDetailed.connect(self.on_canvas_selection_changed)
        self.canvas.itemMoved.connect(self.on_item_moved)
        self.canvas.zoomChanged.connect(self.on_zoom_changed)
        self.canvas.fit_page()
        self.update_window_title()

    def _create_docks(self) -> None:
        property_dock = QDockWidget("Object Properties", self)
        property_dock.setWidget(self.property_panel)
        property_dock.setObjectName("propertyDock")
        property_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, property_dock)

        settings_dock = QDockWidget("Document / Machine", self)
        settings_dock.setWidget(self.settings_panel)
        settings_dock.setObjectName("settingsDock")
        settings_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, settings_dock)

    def _create_actions(self) -> None:
        self.new_action = QAction("New Project", self, shortcut=QKeySequence.StandardKey.New, triggered=self.new_project)
        self.open_action = QAction("Open Project...", self, shortcut=QKeySequence.StandardKey.Open, triggered=self.open_project)
        self.save_action = QAction("Save Project", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.save_project)
        self.save_as_action = QAction("Save Project As...", self, shortcut=QKeySequence.StandardKey.SaveAs, triggered=self.save_project_as)
        self.import_svg_action = QAction("Import SVG...", self, triggered=self.import_svg)
        self.import_image_action = QAction("Import Image...", self, triggered=self.import_image)
        self.add_text_action = QAction("Add Text...", self, triggered=self.add_text)
        self.export_action = QAction("Preview / Export G-Code...", self, shortcut="Ctrl+E", triggered=self.preview_and_export)
        self.exit_action = QAction("Exit", self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close)

        self.undo_action = QAction("Undo", self, shortcut=QKeySequence.StandardKey.Undo, triggered=self.undo)
        self.redo_action = QAction("Redo", self, shortcut=QKeySequence.StandardKey.Redo, triggered=self.redo)
        self.delete_action = QAction("Delete", self, shortcut=QKeySequence.StandardKey.Delete, triggered=self.delete_selected)
        self.duplicate_action = QAction("Duplicate", self, shortcut=QKeySequence("Ctrl+D"), triggered=self.duplicate_selected)
        self.center_action = QAction("Center on Page", self, triggered=self.center_selected_on_page)
        self.align_left_action = QAction("Align Left", self, triggered=lambda: self.align_selected("left"))
        self.align_right_action = QAction("Align Right", self, triggered=lambda: self.align_selected("right"))
        self.align_top_action = QAction("Align Top", self, triggered=lambda: self.align_selected("top"))
        self.align_bottom_action = QAction("Align Bottom", self, triggered=lambda: self.align_selected("bottom"))
        self.bring_front_action = QAction("Bring to Front", self, triggered=self.bring_selected_to_front)
        self.send_back_action = QAction("Send to Back", self, triggered=self.send_selected_to_back)

        self.zoom_fit_action = QAction("Fit Page", self, shortcut="Ctrl+0", triggered=self.canvas.fit_page)
        self.validate_action = QAction("Validate Project", self, triggered=self.validate_project)

    def _create_menus_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.save_as_action,
            self.import_svg_action,
            self.import_image_action,
            self.export_action,
            self.exit_action,
        ]:
            file_menu.addAction(action)

        edit_menu = self.menuBar().addMenu("&Edit")
        for action in [
            self.undo_action,
            self.redo_action,
            self.delete_action,
            self.duplicate_action,
            self.center_action,
            self.align_left_action,
            self.align_right_action,
            self.align_top_action,
            self.align_bottom_action,
            self.bring_front_action,
            self.send_back_action,
        ]:
            edit_menu.addAction(action)

        insert_menu = self.menuBar().addMenu("&Insert")
        insert_menu.addAction(self.add_text_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.zoom_fit_action)
        view_menu.addAction(self.validate_action)

        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
            self.import_svg_action,
            self.import_image_action,
            self.add_text_action,
            self.export_action,
            self.undo_action,
            self.redo_action,
        ]:
            toolbar.addAction(action)
        self.addToolBar(toolbar)

    def update_window_title(self) -> None:
        suffix = "*" if self.modified else ""
        file_name = Path(self.document.file_path).name if self.document.file_path else "Untitled"
        self.setWindowTitle(f"{APP_NAME} - {file_name}{suffix}")

    def set_document(self, document: PlotterDocument, reset_history: bool = False) -> None:
        self.document = document
        self.canvas.document = document
        self.canvas.rebuild_from_document()
        self.settings_panel.load_from_document(document)
        self.property_panel.set_selection(document.selected_objects())
        if reset_history:
            self.history.reset(document)
        self.modified = False
        self.update_window_title()

    def mark_modified(self) -> None:
        if self._suspend_history:
            return
        self.modified = True
        self.history.push(self.document)
        self.update_window_title()

    def ask_save_if_needed(self) -> bool:
        if not self.modified:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The current project has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Cancel:
            return False
        if result == QMessageBox.StandardButton.Save:
            return self.save_project()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.ask_save_if_needed():
            event.accept()
        else:
            event.ignore()

    def new_project(self) -> None:
        if not self.ask_save_if_needed():
            return
        document = PlotterDocument()
        document.profile = copy.deepcopy(self.profile_registry["ELEGOO Neptune 2 Pen Plotter"])
        self.set_document(document, reset_history=True)
        self.canvas.fit_page()

    def open_project(self) -> None:
        if not self.ask_save_if_needed():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", PROJECT_FILE_FILTER)
        if not path:
            return
        try:
            document = load_project(path)
        except ProjectIOError as exc:
            QMessageBox.critical(self, "Open Project Failed", str(exc))
            return
        self.set_document(document, reset_history=True)
        self.canvas.fit_page()

    def save_project(self) -> bool:
        if not self.document.file_path:
            return self.save_project_as()
        try:
            save_project(self.document, self.document.file_path)
        except ProjectIOError as exc:
            QMessageBox.critical(self, "Save Project Failed", str(exc))
            return False
        self.modified = False
        self.update_window_title()
        self.statusBar().showMessage("Project saved.", 3000)
        return True

    def save_project_as(self) -> bool:
        suggested = self.document.file_path or f"untitled{DEFAULT_PROJECT_EXTENSION}"
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", suggested, PROJECT_FILE_FILTER)
        if not path:
            return False
        if not path.endswith(DEFAULT_PROJECT_EXTENSION):
            path += DEFAULT_PROJECT_EXTENSION
        self.document.file_path = path
        return self.save_project()

    def import_svg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import SVG", "", SVG_FILE_FILTER)
        if not path:
            return
        try:
            result = import_svg_file(path, tolerance_mm=self.document.gcode.curve_tolerance_mm)
        except SVGImportError as exc:
            QMessageBox.critical(self, "SVG Import Failed", str(exc))
            return

        from ..document import SvgObject

        svg_object = SvgObject(
            name=Path(path).stem,
            source_name=result.source_name,
            source_path=result.source_path,
            import_notes=result.notes,
            local_polylines=result.polylines,
            x_mm=10.0,
            y_mm=10.0,
        )
        self.document.add_object(svg_object)
        self.document.selected_ids = [svg_object.id]
        self.canvas.refresh_object(svg_object.id)
        self.canvas.apply_selection(self.document.selected_ids)
        self.property_panel.set_selection(self.document.selected_objects())
        self.mark_modified()
        self.statusBar().showMessage(f"Imported SVG: {result.source_name}", 4000)

    def import_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Image", "", IMAGE_FILE_FILTER)
        if not path:
            return

        dialog = RasterImportDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            result = import_raster_file(path, dialog.settings())
        except RasterImportError as exc:
            QMessageBox.critical(self, "Image Import Failed", str(exc))
            return

        if not result.polylines:
            QMessageBox.warning(
                self,
                "Image Import",
                "No plot lines were generated. Lower the darkness threshold, reduce gamma, or increase contrast.",
            )
            return

        raster_object = RasterObject(
            name=Path(path).stem,
            source_name=result.source_name,
            source_path=result.source_path,
            import_notes=result.notes,
            sampled_columns=result.sampled_columns,
            sampled_rows=result.sampled_rows,
            local_polylines=result.polylines,
            x_mm=10.0,
            y_mm=10.0,
        )
        self.document.add_object(raster_object)
        self.document.selected_ids = [raster_object.id]
        self.canvas.refresh_object(raster_object.id)
        self.canvas.apply_selection(self.document.selected_ids)
        self.property_panel.set_selection(self.document.selected_objects())
        self.mark_modified()
        self.statusBar().showMessage(result.notes, 7000)

    def add_text(self) -> None:
        dialog = NewTextDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        obj = dialog.build_text_object()
        obj.x_mm = 20.0
        obj.y_mm = 20.0
        obj.name = "Text"
        self.document.add_object(obj)
        self.document.selected_ids = [obj.id]
        self.canvas.refresh_object(obj.id)
        self.canvas.apply_selection([obj.id])
        self.property_panel.set_selection([obj])
        self.mark_modified()

    def on_canvas_coordinate_changed(self, x: float, y: float) -> None:
        self.coord_display.setText(f"X: {x:.2f} mm   Y: {y:.2f} mm")

    def on_canvas_selection_changed(self, object_ids: list[str]) -> None:
        self.document.selected_ids = object_ids
        self.property_panel.set_selection(self.document.selected_objects())
        self.selection_display.setText(f"Selection: {len(object_ids)}")

    def on_item_moved(self, object_id: str, x_mm: float, y_mm: float) -> None:
        obj = self.document.object_by_id(object_id)
        if obj is None:
            return
        obj.x_mm = x_mm
        obj.y_mm = y_mm
        self.property_panel.set_selection(self.document.selected_objects())
        self.mark_modified()

    def on_zoom_changed(self, zoom: float) -> None:
        self.zoom_display.setText(f"Zoom: {zoom * 100:.0f}%")

    def apply_object_properties(self, payload: dict) -> None:
        obj = self.document.object_by_id(payload["id"])
        if obj is None:
            return
        obj.name = payload["name"]
        obj.x_mm = payload["x_mm"]
        obj.y_mm = payload["y_mm"]
        obj.scale_x = payload["scale_x"]
        obj.scale_y = payload["scale_y"]
        obj.rotation_deg = payload["rotation_deg"]
        if isinstance(obj, TextObject):
            obj.text = payload.get("text", obj.text)
            obj.font_family = payload.get("font_family", obj.font_family)
            obj.font_size_mm = payload.get("font_size_mm", obj.font_size_mm)
            obj.letter_spacing_mm = payload.get("letter_spacing_mm", obj.letter_spacing_mm)
            obj.line_spacing = payload.get("line_spacing", obj.line_spacing)
            obj.rebuild_geometry()
        self.canvas.refresh_object(obj.id)
        self.mark_modified()

    def apply_document_settings(self, page, profile, gcode) -> None:
        self.document.page = page
        self.document.profile = profile
        self.document.gcode = gcode
        self.canvas.rebuild_from_document()
        self.canvas.fit_page()
        self.mark_modified()

    def selected_objects(self):
        return self.document.selected_objects()

    def delete_selected(self) -> None:
        selected_ids = list(self.document.selected_ids)
        if not selected_ids:
            return
        self.document.remove_object_ids(selected_ids)
        self.canvas.rebuild_from_document()
        self.property_panel.set_selection([])
        self.mark_modified()

    def duplicate_selected(self) -> None:
        clones = self.document.duplicate_selected()
        if not clones:
            return
        self.canvas.rebuild_from_document()
        self.property_panel.set_selection(clones if len(clones) == 1 else [])
        self.mark_modified()

    def bring_selected_to_front(self) -> None:
        selected = self.selected_objects()
        if not selected:
            return
        max_z = max((obj.z_order for obj in self.document.objects), default=0)
        for step, obj in enumerate(selected, start=1):
            obj.z_order = max_z + step
        self.document.reindex_z_order()
        self.canvas.rebuild_from_document()
        self.mark_modified()

    def send_selected_to_back(self) -> None:
        selected = self.selected_objects()
        if not selected:
            return
        for step, obj in enumerate(sorted(selected, key=lambda item: item.z_order)):
            obj.z_order = -len(selected) + step
        self.document.reindex_z_order()
        self.canvas.rebuild_from_document()
        self.mark_modified()

    def center_selected_on_page(self) -> None:
        selected = self.selected_objects()
        if not selected:
            return
        page_cx = self.document.page.width_mm / 2.0
        page_cy = self.document.page.height_mm / 2.0
        for obj in selected:
            bbox = obj.world_bbox()
            if bbox is None:
                continue
            centre = bbox.center
            obj.x_mm += page_cx - centre.x
            obj.y_mm += page_cy - centre.y
            self.canvas.refresh_object(obj.id)
        self.property_panel.set_selection(selected)
        self.mark_modified()

    def align_selected(self, mode: str) -> None:
        selected = self.selected_objects()
        if len(selected) < 2:
            return
        boxes = [obj.world_bbox() for obj in selected]
        boxes = [box for box in boxes if box is not None]
        if not boxes:
            return
        if mode == "left":
            target = min(box.min_x for box in boxes)
            for obj in selected:
                bbox = obj.world_bbox()
                if bbox:
                    obj.x_mm += target - bbox.min_x
        elif mode == "right":
            target = max(box.max_x for box in boxes)
            for obj in selected:
                bbox = obj.world_bbox()
                if bbox:
                    obj.x_mm += target - bbox.max_x
        elif mode == "top":
            target = min(box.min_y for box in boxes)
            for obj in selected:
                bbox = obj.world_bbox()
                if bbox:
                    obj.y_mm += target - bbox.min_y
        elif mode == "bottom":
            target = max(box.max_y for box in boxes)
            for obj in selected:
                bbox = obj.world_bbox()
                if bbox:
                    obj.y_mm += target - bbox.max_y
        for obj in selected:
            self.canvas.refresh_object(obj.id)
        self.property_panel.set_selection(selected)
        self.mark_modified()

    def validate_project(self) -> None:
        issues = validate_document(self.document)
        if not issues:
            QMessageBox.information(self, "Validation", "No validation issues found.")
            return
        QMessageBox.information(self, "Validation", "\n".join(issue.as_text() for issue in issues))

    def preview_and_export(self) -> None:
        issues = validate_document(self.document)
        if any(issue.severity == "error" for issue in issues):
            reply = QMessageBox.question(
                self,
                "Validation Errors",
                "The project has validation errors. Open preview anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            result = generate_gcode(self.document)
        except Exception as exc:
            QMessageBox.critical(self, "G-Code Generation Failed", str(exc))
            return
        dialog = PreviewDialog(self.document, result, issues, self)
        if dialog.exec() == dialog.DialogCode.Accepted and dialog.saved_path:
            self.statusBar().showMessage(f"G-Code saved to {dialog.saved_path}", 4000)

    def undo(self) -> None:
        snapshot = self.history.undo()
        if snapshot is None:
            return
        restored = PlotterDocument.from_dict(snapshot)
        restored.file_path = self.document.file_path
        self.document = restored
        self.canvas.document = restored
        self.canvas.rebuild_from_document()
        self.settings_panel.load_from_document(restored)
        self.property_panel.set_selection(restored.selected_objects())
        self.modified = True
        self.update_window_title()

    def redo(self) -> None:
        snapshot = self.history.redo()
        if snapshot is None:
            return
        restored = PlotterDocument.from_dict(snapshot)
        restored.file_path = self.document.file_path
        self.document = restored
        self.canvas.document = restored
        self.canvas.rebuild_from_document()
        self.settings_panel.load_from_document(restored)
        self.property_panel.set_selection(restored.selected_objects())
        self.modified = True
        self.update_window_title()
