from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..document import DocumentObject, TextObject


class PropertyPanel(QWidget):
    propertiesApplied = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_object: DocumentObject | None = None

        self.info_label = QLabel("No object selected.")
        self.info_label.setWordWrap(True)

        self.name_edit = QLineEdit()
        self.x_spin = self._make_spin(-10000.0, 10000.0, 3)
        self.y_spin = self._make_spin(-10000.0, 10000.0, 3)
        self.scale_x_spin = self._make_spin(-100.0, 100.0, 4, value=1.0)
        self.scale_y_spin = self._make_spin(-100.0, 100.0, 4, value=1.0)
        self.rotation_spin = self._make_spin(-3600.0, 3600.0, 3)

        common_group = QGroupBox("Transform")
        common_layout = QFormLayout(common_group)
        common_layout.addRow("Name", self.name_edit)
        common_layout.addRow("X [mm]", self.x_spin)
        common_layout.addRow("Y [mm]", self.y_spin)
        common_layout.addRow("Scale X", self.scale_x_spin)
        common_layout.addRow("Scale Y", self.scale_y_spin)
        common_layout.addRow("Rotation [°]", self.rotation_spin)

        self.text_edit = QPlainTextEdit()
        self.font_combo = QComboBox()
        self.font_combo.addItems(sorted(QFontDatabase.families()))
        self.font_size_spin = self._make_spin(0.5, 300.0, 2, value=12.0)
        self.spacing_spin = self._make_spin(-10.0, 50.0, 3, value=0.0)
        self.line_spacing_spin = self._make_spin(0.5, 5.0, 2, value=1.2)

        text_group = QGroupBox("Text")
        text_layout = QFormLayout(text_group)
        text_layout.addRow("Content", self.text_edit)
        text_layout.addRow("Font", self.font_combo)
        text_layout.addRow("Size [mm]", self.font_size_spin)
        text_layout.addRow("Letter spacing [mm]", self.spacing_spin)
        text_layout.addRow("Line spacing", self.line_spacing_spin)

        self.apply_button = QPushButton("Apply Changes")
        self.apply_button.clicked.connect(self._emit_changes)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(common_group)
        layout.addWidget(text_group)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

        self.common_group = common_group
        self.text_group = text_group
        self._set_enabled(False)

    def _make_spin(self, minimum: float, maximum: float, decimals: int, value: float = 0.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(1.0 if decimals <= 2 else 0.1)
        return spin

    def _set_enabled(self, enabled: bool, text_fields: bool | None = None) -> None:
        self.common_group.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        if text_fields is None:
            self.text_group.setEnabled(enabled)
        else:
            self.text_group.setEnabled(text_fields)

    def set_selection(self, objects: list[DocumentObject]) -> None:
        self._current_object = None
        if not objects:
            self.info_label.setText("No object selected.")
            self._set_enabled(False)
            return
        if len(objects) > 1:
            self.info_label.setText(f"{len(objects)} objects selected. Transform editing stays single-object only.")
            self._set_enabled(False)
            return

        obj = objects[0]
        self._current_object = obj
        self.info_label.setText(f"Selected: {obj.name} ({obj.object_type})")

        for widget, value in [
            (self.name_edit, obj.name),
        ]:
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)

        for spin, value in [
            (self.x_spin, obj.x_mm),
            (self.y_spin, obj.y_mm),
            (self.scale_x_spin, obj.scale_x),
            (self.scale_y_spin, obj.scale_y),
            (self.rotation_spin, obj.rotation_deg),
        ]:
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

        is_text = isinstance(obj, TextObject)
        self._set_enabled(True, text_fields=is_text)
        if is_text:
            assert isinstance(obj, TextObject)
            self.text_edit.setPlainText(obj.text)
            index = self.font_combo.findText(obj.font_family)
            self.font_combo.setCurrentIndex(max(index, 0))
            self.font_size_spin.setValue(obj.font_size_mm)
            self.spacing_spin.setValue(obj.letter_spacing_mm)
            self.line_spacing_spin.setValue(obj.line_spacing)
        else:
            self.text_edit.clear()

    def _emit_changes(self) -> None:
        if self._current_object is None:
            return
        payload = {
            "id": self._current_object.id,
            "name": self.name_edit.text().strip() or self._current_object.name,
            "x_mm": self.x_spin.value(),
            "y_mm": self.y_spin.value(),
            "scale_x": self.scale_x_spin.value(),
            "scale_y": self.scale_y_spin.value(),
            "rotation_deg": self.rotation_spin.value(),
        }
        if isinstance(self._current_object, TextObject):
            payload.update(
                {
                    "text": self.text_edit.toPlainText(),
                    "font_family": self.font_combo.currentText(),
                    "font_size_mm": self.font_size_spin.value(),
                    "letter_spacing_mm": self.spacing_spin.value(),
                    "line_spacing": self.line_spacing_spin.value(),
                }
            )
        self.propertiesApplied.emit(payload)
