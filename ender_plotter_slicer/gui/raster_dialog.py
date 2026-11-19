from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..raster_importer import (
    RasterImportCancelled,
    RasterImportError,
    RasterImportResult,
    RasterImportSettings,
    import_raster_file,
    load_raster_image,
    raster_presets,
)
from ..raster_preview import render_pencil_preview


class _ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumSize(220, 240)
        self.setBackgroundBrush(Qt.GlobalColor.white)

    def set_image(self, image):
        self.scene().clear()
        self.scene().addPixmap(QPixmap.fromImage(ImageQt(image)))
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        if 0.05 <= self.transform().m11() * factor <= 30:
            self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class _RasterWorker(QThread):
    progress = Signal(int, str)

    def __init__(self, path, settings, parent=None):
        super().__init__(parent)
        self.path, self.settings = path, settings
        self.result: RasterImportResult | None = None
        self.image = None
        self.error = ""
        self.cancelled = False

    def run(self):
        try:
            self.result = import_raster_file(
                self.path, self.settings,
                lambda p, text: self.progress.emit(round(p * 0.92), text), self.isInterruptionRequested,
            )
            self.progress.emit(94, "Rendering actual pencil paths")
            self.image = render_pencil_preview(
                self.result.polylines, self.result.width_mm, self.result.height_mm,
                self.settings.pencil_width_mm, self.settings.stroke_opacity,
                cancel=self.isInterruptionRequested,
            )
        except RasterImportCancelled:
            self.cancelled = True
            self.result = None
        except Exception as exc:
            self.error = str(exc)
            self.result = None


class RasterImportDialog(QDialog):
    """Preview and accept the same paths; never silently regenerate on import."""
    def __init__(self, path: str, parent=None, settings: RasterImportSettings | None = None):
        super().__init__(parent)
        self.path = path
        self.result: RasterImportResult | None = None
        self._worker: _RasterWorker | None = None
        self._loading = True
        self._close_when_idle = False
        self._accepted_settings = None
        self.presets = raster_presets()
        self.setWindowTitle(f"Pencil Drawing · {Path(path).name}")
        self.resize(1280, 800)
        self.setMinimumSize(800, 520)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([*self.presets, "Custom"])
        self.style_combo = QComboBox()
        for label, value in (("Tonal crosshatching", "crosshatch"), ("Form-following pencil", "flow"),
                             ("Legacy horizontal scanlines", "scanline")):
            self.style_combo.addItem(label, value)
        self.controls = {"style": self.style_combo}
        form = QFormLayout()
        form.addRow("Preset", self.preset_combo)
        form.addRow("Drawing style", self.style_combo)
        specs = [
            ("width_mm", "Target width", 5, 220, 2, " mm"),
            ("max_height_mm", "Max height", 5, 220, 2, " mm"),
            ("horizontal_resolution_mm", "Sample distance", 0.05, 5, 3, " mm"),
            ("line_spacing_mm", "Minimum hatch spacing", 0.05, 5, 3, " mm"),
            ("tone_layers", "Shadow layers / directions", 1, 8, 0, ""),
            ("hatch_angle_deg", "Main hatch angle", -180, 180, 1, "°"),
            ("pencil_width_mm", "Measured pencil width", 0.05, 3, 2, " mm"),
            ("stroke_opacity", "Stroke darkness (0–1)", 0.05, 1, 2, ""),
            ("darkness_threshold", "Highlight cutoff (0–1)", 0, 1, 3, ""),
            ("contrast", "Contrast", 0.1, 5, 2, ""),
            ("gamma", "Tone gamma", 0.1, 5, 2, ""),
            ("smoothing_mm", "Noise smoothing", 0, 3, 2, " mm"),
            ("flow_smoothing_mm", "Direction smoothing (flow)", 0, 10, 2, " mm"),
            ("stroke_length_mm", "Stroke length (flow)", 1, 80, 1, " mm"),
            ("seed", "Reproducible seed (flow)", 0, 2**31 - 1, 0, ""),
            ("min_segment_mm", "Minimum stroke length", 0, 10, 2, " mm"),
            ("merge_gap_mm", "Merge gaps (legacy only)", 0, 10, 2, " mm"),
        ]
        for name, label, low, high, decimals, suffix in specs:
            spin = QDoubleSpinBox() if decimals else QSpinBox()
            spin.setRange(low, high)
            if decimals:
                spin.setDecimals(decimals)
                spin.setSingleStep(0.05 if high <= 10 else 1.0)
            spin.setSuffix(suffix)
            spin.setObjectName(name)
            self.controls[name] = spin
            form.addRow(label, spin)
            spin.valueChanged.connect(self._changed)
        for name, label in (("auto_contrast", "Use full source tonal range"), ("invert", "Invert brightness")):
            check = QCheckBox(label)
            self.controls[name] = check
            check.toggled.connect(self._changed)
            form.addRow(check)
        self.controls["gamma"].setToolTip("Below 1 darkens midtones. Above 1 lightens midtones.")
        self.controls["pencil_width_mm"].setToolTip("Measure one plotted stroke. Width controls both tone allocation and the preview.")
        self.controls["stroke_opacity"].setToolTip("Approximate darkness of one stroke on paper. No Z pressure changes are generated.")
        self.controls["merge_gap_mm"].setToolTip("Only legacy mode bridges gaps. Pencil modes keep highlights open.")
        self.controls["horizontal_resolution_mm"].setToolTip("Smaller values preserve finer image detail and require more computation.")
        self.style_combo.currentIndexChanged.connect(self._changed)
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        self.form_widget = QWidget()
        self.form_widget.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_widget)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(440)

        self.source_view, self.plot_view = _ImageView(), _ImageView()
        images = QSplitter()
        for label, view in (("Source image", self.source_view), ("Actual plot paths · approximate graphite on paper", self.plot_view)):
            panel = QWidget()
            layout = QVBoxLayout(panel)
            layout.addWidget(QLabel(label))
            layout.addWidget(view, 1)
            images.addWidget(panel)
        main = QSplitter()
        main.addWidget(scroll)
        main.addWidget(images)
        main.setStretchFactor(1, 1)
        main.setSizes([370, 900])
        self.status_label = QLabel("Build a preview, then import the drawing.")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.preview_button = QPushButton("Update Preview")
        self.preview_button.clicked.connect(self.build_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.import_button.setText("Import Drawing")
        self.import_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.preview_button)
        row.addStretch()
        row.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(main, 1)
        layout.addWidget(QLabel("Wheel: zoom · Drag: pan · Double-click: fit. The preview uses fixed pressure and the entered stroke width."))
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(row)
        self._load_settings(settings or self.presets["Pencil · balanced"])
        if settings:
            self._loading = True
            name = next((name for name, preset in self.presets.items()
                         if all(getattr(settings, key) == value for key, value in asdict(preset).items()
                                if key not in {"width_mm", "max_height_mm"})), "Custom")
            self.preset_combo.setCurrentText(name)
            self._loading = False
        try:
            source = load_raster_image(path)
            source.thumbnail((1400, 1400))
            self.source_view.set_image(source)
        except RasterImportError as exc:
            self.status_label.setText(str(exc))
        else:
            QTimer.singleShot(0, self.build_preview)
        self._loading = False

    def _load_settings(self, settings):
        self._loading = True
        for item in fields(settings):
            control = self.controls[item.name]
            value = getattr(settings, item.name)
            if isinstance(control, QComboBox):
                control.setCurrentIndex(control.findData(value))
            elif isinstance(control, QCheckBox):
                control.setChecked(value)
            else:
                control.setValue(value)
        self._loading = False
        self._update_enabled()

    def _update_enabled(self):
        style = self.style_combo.currentData()
        for name in ("flow_smoothing_mm", "stroke_length_mm", "seed"):
            self.controls[name].setEnabled(style == "flow")
        self.controls["merge_gap_mm"].setEnabled(style == "scanline")
        self.controls["hatch_angle_deg"].setEnabled(style != "scanline")

    def _preset_changed(self, name):
        if self._loading or name not in self.presets:
            return
        width = self.controls["width_mm"].value()
        height = self.controls["max_height_mm"].value()
        self._load_settings(self.presets[name])
        self._loading = True
        self.controls["width_mm"].setValue(width)
        self.controls["max_height_mm"].setValue(height)
        self._loading = False
        self._invalidate()

    def _changed(self, *args):
        if not self._loading:
            self.preset_combo.setCurrentText("Custom")
            self._update_enabled()
            self._invalidate()

    def _invalidate(self):
        self.result = None
        self._accepted_settings = None
        self.import_button.setEnabled(False)
        self.status_label.setText("Settings changed. Update the preview before importing.")

    def settings(self) -> RasterImportSettings:
        values = {}
        for name, control in self.controls.items():
            values[name] = (control.currentData() if isinstance(control, QComboBox) else
                            control.isChecked() if isinstance(control, QCheckBox) else control.value())
        return RasterImportSettings(**values)

    @property
    def settings_dict(self):
        return asdict(self._accepted_settings) if self._accepted_settings else {}

    def build_preview(self):
        if self._worker:
            self._worker.requestInterruption()
            self.preview_button.setEnabled(False)
            self.status_label.setText("Cancelling conversion…")
            return
        self._invalidate()
        self.form_widget.setEnabled(False)
        self.progress_bar.setValue(0)
        self.preview_button.setText("Cancel Conversion")
        self._worker = _RasterWorker(self.path, self.settings(), self)
        self._worker.progress.connect(self._progress)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.status_label.setText(text)

    def _finished(self):
        worker = self._worker
        self._worker = None
        self.form_widget.setEnabled(True)
        self._update_enabled()
        self.preview_button.setEnabled(True)
        self.preview_button.setText("Update Preview")
        if self._close_when_idle:
            worker.deleteLater()
            super().reject()
            return
        if worker.cancelled:
            self.status_label.setText("Conversion cancelled. Change the settings or build another preview.")
        elif worker.error:
            self.status_label.setText(f"Conversion failed: {worker.error}")
        else:
            self.result = worker.result
            self._accepted_settings = worker.settings
            self.plot_view.set_image(worker.image)
            length = sum(line.length() for line in self.result.polylines)
            self.status_label.setText(f"{self.result.notes} Draw length: {length / 1000:.2f} m."
                                     + (" No strokes: lower the highlight cutoff or gamma." if not self.result.polylines else ""))
            self.progress_bar.setValue(100)
            self.import_button.setEnabled(bool(self.result.polylines))
        worker.deleteLater()

    def accept(self):
        if self.result and self.result.polylines and not self._worker:
            super().accept()

    def reject(self):
        if self._worker:
            self._close_when_idle = True
            self._worker.requestInterruption()
            self.preview_button.setEnabled(False)
            self.status_label.setText("Cancelling conversion…")
        else:
            super().reject()

    def closeEvent(self, event):
        if self._worker:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
