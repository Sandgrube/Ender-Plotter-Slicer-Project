from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config import GCODE_FILE_FILTER
from ..document import PlotterDocument, TextObject
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


class _MachinePreviewView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Machine coordinates have +Y upwards; Qt scenes have +Y downwards.
        self.scale(1, -1)

    def fit_paths(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_paths()

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_paths()

    def mouseDoubleClickEvent(self, event):
        self.fit_paths()

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        if 0.05 <= abs(self.transform().m11()) * factor <= 50:
            self.scale(factor, factor)


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
        self.view = _MachinePreviewView(self.scene)
        self._populate_scene()
        self.show_travel = QCheckBox("Show pen-up travel")
        self.show_travel.toggled.connect(self.travel_item.setVisible)

        self.gcode_preview = QPlainTextEdit()
        shown_lines = result.lines[:4000]
        if len(result.lines) > len(shown_lines):
            shown_lines = [*shown_lines, f"; Preview truncated at 4,000 of {len(result.lines):,} lines. Save exports the complete G-code."]
        self.gcode_preview.setPlainText("\n".join(shown_lines))
        self.gcode_preview.setReadOnly(True)
        self.gcode_preview.setFont(QFont("Courier New", 10))

        self.issue_list = QListWidget()
        for issue in issues:
            self.issue_list.addItem(issue.as_text())
        if not issues:
            self.issue_list.addItem("No validation issues.")

        minutes = result.stats.motion_time_lower_bound_s / 60
        stats_label = QLabel(
            f"Paths: {result.stats.path_count}    "
            f"Draw length: {result.stats.draw_length_mm:.1f} mm    "
            f"Travel length: {result.stats.travel_length_mm:.1f} mm\n"
            f"Motion time ≥ {int(minutes // 60)} h {int(minutes % 60)} min (includes pen lifts).\n"
            "Homing, acceleration, dwell and custom start/end commands add time."
        )
        stats_label.setWordWrap(True)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Machine paths · X →, Y ↑ · Wheel: zoom · Double-click: fit"))
        left_layout.addWidget(self.view, 1)
        left_layout.addWidget(self.show_travel)
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
        # Two graphics items handle dense drawings without creating one Qt
        # object per G-code move. Keep travel separate so it cannot hide tone.
        draw_path, travel_path = QPainterPath(), QPainterPath()
        for segment in self.result.preview.segments:
            path = draw_path if segment.is_draw else travel_path
            path.moveTo(segment.start.x, segment.start.y)
            path.lineTo(segment.end.x, segment.end.y)
        self.scene.addPath(draw_path, QPen(QColor("#303030"), 0))
        travel_pen = QPen(QColor("#9aa8b8"), 0, Qt.PenStyle.DashLine)
        self.travel_item = self.scene.addPath(travel_path, travel_pen)
        self.travel_item.setVisible(False)
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
