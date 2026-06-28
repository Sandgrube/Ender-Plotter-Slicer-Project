from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QMessageBox,
)

from ..config import GCODE_FILE_FILTER
from ..document import PlotterDocument, TextObject
from ..raster_importer import RasterImportSettings
from ..gcode import GCodeResult
from ..validator import ValidationIssue


class NewTextDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Text")
        self.text_edit = QPlainTextEdit("Hello Plotter")
        self.font_combo = QComboBox()
        from PySide6.QtGui import QFontDatabase

        self.font_combo.addItems(sorted(QFontDatabase.families()))
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1.0, 300.0)
        self.size_spin.setValue(14.0)
        self.size_spin.setSuffix(" mm")
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(-10.0, 50.0)
        self.spacing_spin.setDecimals(3)
        self.spacing_spin.setValue(0.0)

        form = QFormLayout()
        form.addRow("Text", self.text_edit)
        form.addRow("Font", self.font_combo)
        form.addRow("Size", self.size_spin)
        form.addRow("Letter spacing", self.spacing_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def build_text_object(self) -> TextObject:
        obj = TextObject(
            name="Text",
            text=self.text_edit.toPlainText(),
            font_family=self.font_combo.currentText(),
            font_size_mm=self.size_spin.value(),
            letter_spacing_mm=self.spacing_spin.value(),
        )
        obj.rebuild_geometry()
        return obj


class RasterImportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Raster Image")
        self.resize(460, 420)

        self.width_spin = self._make_spin(5.0, 220.0, 2, 120.0, " mm")
        self.max_height_spin = self._make_spin(5.0, 220.0, 2, 180.0, " mm")
        self.x_resolution_spin = self._make_spin(0.05, 5.0, 3, 0.35, " mm")
        self.line_spacing_spin = self._make_spin(0.05, 5.0, 3, 0.45, " mm")
        self.threshold_spin = self._make_spin(0.0, 100.0, 1, 35.0, " %")
        self.tone_layers_spin = QSpinBox()
        self.tone_layers_spin.setRange(1, 8)
        self.tone_layers_spin.setValue(3)
        self.contrast_spin = self._make_spin(0.1, 5.0, 2, 1.0, "")
        self.gamma_spin = self._make_spin(0.1, 5.0, 2, 1.0, "")
        self.min_segment_spin = self._make_spin(0.0, 10.0, 2, 0.60, " mm")
        self.merge_gap_spin = self._make_spin(0.0, 10.0, 2, 0.35, " mm")
        self.invert_check = QCheckBox("Invert brightness")

        help_label = QLabel(
            "Dark pixels become plot lines. More tone layers create denser hatching in darker areas. "
            "Use one tone layer for clean line-art or logos."
        )
        help_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Target width", self.width_spin)
        form.addRow("Max height", self.max_height_spin)
        form.addRow("Horizontal sample", self.x_resolution_spin)
        form.addRow("Line spacing", self.line_spacing_spin)
        form.addRow("Darkness threshold", self.threshold_spin)
        form.addRow("Tone layers", self.tone_layers_spin)
        form.addRow("Contrast", self.contrast_spin)
        form.addRow("Gamma", self.gamma_spin)
        form.addRow("Minimum segment", self.min_segment_spin)
        form.addRow("Merge small gaps", self.merge_gap_spin)
        form.addRow(self.invert_check)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _make_spin(self, minimum: float, maximum: float, decimals: int, value: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSingleStep(1.0 if decimals <= 1 else 0.1)
        spin.setSuffix(suffix)
        return spin

    def settings(self) -> RasterImportSettings:
        return RasterImportSettings(
            width_mm=self.width_spin.value(),
            max_height_mm=self.max_height_spin.value(),
            horizontal_resolution_mm=self.x_resolution_spin.value(),
            line_spacing_mm=self.line_spacing_spin.value(),
            darkness_threshold=self.threshold_spin.value() / 100.0,
            tone_layers=self.tone_layers_spin.value(),
            contrast=self.contrast_spin.value(),
            gamma=self.gamma_spin.value(),
            invert=self.invert_check.isChecked(),
            min_segment_mm=self.min_segment_spin.value(),
            merge_gap_mm=self.merge_gap_spin.value(),
        )


class PreviewDialog(QDialog):
    def __init__(self, document: PlotterDocument, result: GCodeResult, issues: list[ValidationIssue], parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.result = result
        self.issues = issues
        self.saved_path: str | None = None

        self.setWindowTitle("Plot Preview and G-Code")
        self.resize(1200, 760)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self._populate_scene()

        self.gcode_preview = QPlainTextEdit()
        self.gcode_preview.setPlainText(result.gcode)
        self.gcode_preview.setReadOnly(True)
        self.gcode_preview.setFont(QFont("Courier New", 10))

        self.issue_list = QListWidget()
        for issue in issues:
            self.issue_list.addItem(issue.as_text())
        if not issues:
            self.issue_list.addItem("No validation issues.")

        stats_label = QLabel(
            f"Paths: {result.stats.path_count}    "
            f"Draw length: {result.stats.draw_length_mm:.1f} mm    "
            f"Travel length: {result.stats.travel_length_mm:.1f} mm"
        )

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Machine-Space Path Preview"))
        left_layout.addWidget(self.view, 1)
        left_layout.addWidget(stats_label)
        left_layout.addWidget(QLabel("Validation"))
        left_layout.addWidget(self.issue_list, 0)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Generated G-Code"))
        right_layout.addWidget(self.gcode_preview, 1)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([500, 700])

        self.save_button = QPushButton("Save G-Code...")
        self.save_button.clicked.connect(self._save_gcode)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(button_row)

    def _populate_scene(self) -> None:
        profile = self.document.profile
        work_rect = QRectF(
            profile.work_offset_x_mm,
            profile.work_offset_y_mm,
            profile.work_area_width_mm,
            profile.work_area_height_mm,
        )
        self.scene.clear()
        self.scene.setSceneRect(work_rect.adjusted(-10, -10, 10, 10))
        self.scene.addRect(work_rect, QPen(QColor("#b7c3d0")), QColor("white"))
        for segment in self.result.preview.segments:
            pen = QPen(QColor("#2b6ef2") if segment.is_draw else QColor("#9aa8b8"))
            pen.setWidthF(0)
            if not segment.is_draw:
                pen.setStyle(Qt.PenStyle.DashLine)
            self.scene.addLine(segment.start.x, segment.start.y, segment.end.x, segment.end.y, pen)
        self.view.fitInView(work_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _save_gcode(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save G-Code", "", GCODE_FILE_FILTER)
        if not path:
            return
        try:
            Path(path).write_text(self.result.gcode, encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save G-Code:\n{exc}")
            return
        self.saved_path = path
        self.accept()
