from __future__ import annotations

import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QScrollArea,
    QFrame,
)

from ..document import GCodeSettings, PageSettings, PlotterDocument
from ..profiles import MachineProfile


class SettingsPanel(QWidget):
    settingsApplied = Signal(object, object, object)

    def __init__(self, profile_registry: dict[str, MachineProfile], parent=None) -> None:
        super().__init__(parent)
        self.profile_registry = profile_registry
        self._loading = False

        self.page_width_spin = self._make_spin(10.0, 2000.0, 2, 210.0)
        self.page_height_spin = self._make_spin(10.0, 2000.0, 2, 297.0)
        self.grid_spin = self._make_spin(0.5, 100.0, 2, 5.0)
        self.grid_check = QCheckBox("Show grid")
        self.snap_check = QCheckBox("Snap to grid")

        page_group = QGroupBox("Page / Canvas")
        page_layout = QFormLayout(page_group)
        page_layout.addRow("Width [mm]", self.page_width_spin)
        page_layout.addRow("Height [mm]", self.page_height_spin)
        page_layout.addRow("Grid [mm]", self.grid_spin)
        page_layout.addRow(self.grid_check)
        page_layout.addRow(self.snap_check)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(sorted(profile_registry.keys()))
        self.profile_combo.currentTextChanged.connect(self._load_selected_profile_into_fields)

        self.work_area_width_spin = self._make_spin(10.0, 2000.0, 2, 220.0)
        self.work_area_height_spin = self._make_spin(10.0, 2000.0, 2, 220.0)
        self.home_check = QCheckBox("Home before plotting")
        self.pen_up_spin = self._make_spin(-20.0, 100.0, 3, 4.5)
        self.pen_down_spin = self._make_spin(-20.0, 100.0, 3, 0.2)
        self.retract_spin = self._make_spin(-20.0, 100.0, 3, 8.0)
        self.travel_feed_spin = self._make_spin(10.0, 50000.0, 1, 3600.0)
        self.plot_feed_spin = self._make_spin(10.0, 50000.0, 1, 1400.0)
        self.z_feed_spin = self._make_spin(10.0, 20000.0, 1, 500.0)
        self.offset_x_spin = self._make_spin(-1000.0, 1000.0, 2, 10.0)
        self.offset_y_spin = self._make_spin(-1000.0, 1000.0, 2, 10.0)
        self.safe_x_spin = self._make_spin(-1000.0, 1000.0, 2, 10.0)
        self.safe_y_spin = self._make_spin(-1000.0, 1000.0, 2, 10.0)
        self.margin_spin = self._make_spin(0.0, 100.0, 2, 3.0)
        self.mirror_x_check = QCheckBox("Mirror X")
        self.mirror_y_check = QCheckBox("Mirror Y")
        self.swap_xy_check = QCheckBox("Swap X/Y")
        self.output_rotation_spin = self._make_spin(-360.0, 360.0, 2, 0.0)
        self.start_gcode_edit = QPlainTextEdit()
        self.end_gcode_edit = QPlainTextEdit()

        profile_group = QGroupBox("Machine Profile")
        profile_layout = QFormLayout(profile_group)
        profile_layout.addRow("Profile", self.profile_combo)
        profile_layout.addRow("Work area width", self.work_area_width_spin)
        profile_layout.addRow("Work area height", self.work_area_height_spin)
        profile_layout.addRow(self.home_check)
        profile_layout.addRow("Pen-up Z", self.pen_up_spin)
        profile_layout.addRow("Pen-down Z", self.pen_down_spin)
        profile_layout.addRow("Retract Z", self.retract_spin)
        profile_layout.addRow("Travel F", self.travel_feed_spin)
        profile_layout.addRow("Plot F", self.plot_feed_spin)
        profile_layout.addRow("Z F", self.z_feed_spin)
        profile_layout.addRow("Work offset X", self.offset_x_spin)
        profile_layout.addRow("Work offset Y", self.offset_y_spin)
        profile_layout.addRow("Safe X", self.safe_x_spin)
        profile_layout.addRow("Safe Y", self.safe_y_spin)
        profile_layout.addRow("Safety margin", self.margin_spin)
        profile_layout.addRow(self.mirror_x_check)
        profile_layout.addRow(self.mirror_y_check)
        profile_layout.addRow(self.swap_xy_check)
        profile_layout.addRow("Output rotation", self.output_rotation_spin)
        profile_layout.addRow("Start G-Code", self.start_gcode_edit)
        profile_layout.addRow("End G-Code", self.end_gcode_edit)

        self.optimize_check = QCheckBox("Optimize plot order")
        self.include_comments_check = QCheckBox("Write comments")
        self.keep_pen_check = QCheckBox("Keep pen down on touching paths")
        self.curve_tolerance_spin = self._make_spin(0.05, 5.0, 3, 0.35)
        self.join_tolerance_spin = self._make_spin(0.01, 10.0, 3, 0.2)

        gcode_group = QGroupBox("G-Code Settings")
        gcode_layout = QFormLayout(gcode_group)
        gcode_layout.addRow(self.optimize_check)
        gcode_layout.addRow(self.include_comments_check)
        gcode_layout.addRow(self.keep_pen_check)
        gcode_layout.addRow("Curve tolerance [mm]", self.curve_tolerance_spin)
        gcode_layout.addRow("Join tolerance [mm]", self.join_tolerance_spin)

        self.apply_button = QPushButton("Apply Settings")
        self.apply_button.clicked.connect(self._emit_settings)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(page_group)
        layout.addWidget(profile_group)
        layout.addWidget(gcode_group)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        if self.profile_combo.count():
            self._load_selected_profile_into_fields(self.profile_combo.currentText())

    def _make_spin(self, minimum: float, maximum: float, decimals: int, value: float = 0.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(1.0 if decimals <= 2 else 0.1)
        return spin

    def _load_profile_fields(self, profile: MachineProfile) -> None:
        self._loading = True
        try:
            for spin, value in [
                (self.work_area_width_spin, profile.work_area_width_mm),
                (self.work_area_height_spin, profile.work_area_height_mm),
                (self.pen_up_spin, profile.pen_up_z_mm),
                (self.pen_down_spin, profile.pen_down_z_mm),
                (self.retract_spin, profile.retract_z_mm),
                (self.travel_feed_spin, profile.travel_feed_mm_min),
                (self.plot_feed_spin, profile.plot_feed_mm_min),
                (self.z_feed_spin, profile.z_feed_mm_min),
                (self.offset_x_spin, profile.work_offset_x_mm),
                (self.offset_y_spin, profile.work_offset_y_mm),
                (self.safe_x_spin, profile.safe_start_x_mm),
                (self.safe_y_spin, profile.safe_start_y_mm),
                (self.margin_spin, profile.safety_margin_mm),
                (self.output_rotation_spin, profile.output_rotation_deg),
            ]:
                spin.setValue(value)

            self.home_check.setChecked(profile.home_enabled)
            self.mirror_x_check.setChecked(profile.mirror_x)
            self.mirror_y_check.setChecked(profile.mirror_y)
            self.swap_xy_check.setChecked(profile.swap_xy)
            self.start_gcode_edit.setPlainText(profile.start_gcode)
            self.end_gcode_edit.setPlainText(profile.end_gcode)
        finally:
            self._loading = False

    def _load_selected_profile_into_fields(self, profile_name: str) -> None:
        if self._loading or profile_name not in self.profile_registry:
            return
        self._load_profile_fields(copy.deepcopy(self.profile_registry[profile_name]))

    def load_from_document(self, document: PlotterDocument) -> None:
        self._loading = True
        try:
            page = document.page
            profile = document.profile
            gcode = document.gcode

            for spin, value in [
                (self.page_width_spin, page.width_mm),
                (self.page_height_spin, page.height_mm),
                (self.grid_spin, page.grid_mm),
                (self.curve_tolerance_spin, gcode.curve_tolerance_mm),
                (self.join_tolerance_spin, gcode.join_tolerance_mm),
            ]:
                spin.setValue(value)

            self.grid_check.setChecked(page.show_grid)
            self.snap_check.setChecked(page.snap_enabled)

            index = self.profile_combo.findText(profile.name)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)

            self.optimize_check.setChecked(gcode.optimize_order)
            self.include_comments_check.setChecked(gcode.include_comments)
            self.keep_pen_check.setChecked(gcode.keep_pen_down_on_touching_paths)
            self._load_profile_fields(profile)
        finally:
            self._loading = False

    def _emit_settings(self) -> None:
        page = PageSettings(
            width_mm=self.page_width_spin.value(),
            height_mm=self.page_height_spin.value(),
            grid_mm=self.grid_spin.value(),
            show_grid=self.grid_check.isChecked(),
            snap_enabled=self.snap_check.isChecked(),
        )
        profile = MachineProfile(
            name=self.profile_combo.currentText(),
            work_area_width_mm=self.work_area_width_spin.value(),
            work_area_height_mm=self.work_area_height_spin.value(),
            work_offset_x_mm=self.offset_x_spin.value(),
            work_offset_y_mm=self.offset_y_spin.value(),
            origin_mode="top_left",
            safe_start_x_mm=self.safe_x_spin.value(),
            safe_start_y_mm=self.safe_y_spin.value(),
            home_enabled=self.home_check.isChecked(),
            pen_up_z_mm=self.pen_up_spin.value(),
            pen_down_z_mm=self.pen_down_spin.value(),
            retract_z_mm=self.retract_spin.value(),
            travel_feed_mm_min=self.travel_feed_spin.value(),
            plot_feed_mm_min=self.plot_feed_spin.value(),
            z_feed_mm_min=self.z_feed_spin.value(),
            safety_margin_mm=self.margin_spin.value(),
            start_gcode=self.start_gcode_edit.toPlainText().strip(),
            end_gcode=self.end_gcode_edit.toPlainText().strip(),
            mirror_x=self.mirror_x_check.isChecked(),
            mirror_y=self.mirror_y_check.isChecked(),
            swap_xy=self.swap_xy_check.isChecked(),
            output_rotation_deg=self.output_rotation_spin.value(),
        )
        gcode = GCodeSettings(
            optimize_order=self.optimize_check.isChecked(),
            curve_tolerance_mm=self.curve_tolerance_spin.value(),
            join_tolerance_mm=self.join_tolerance_spin.value(),
            include_comments=self.include_comments_check.isChecked(),
            keep_pen_down_on_touching_paths=self.keep_pen_check.isChecked(),
        )
        self.settingsApplied.emit(page, profile, gcode)
