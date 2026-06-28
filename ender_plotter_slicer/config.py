from __future__ import annotations

APP_NAME = "Ender Plotter Slicer"
APP_ORG = "Mission Proton"
APP_VERSION = "1.1.0"
PROJECT_FILE_FILTER = "Plotter Projects (*.plotproj.json)"
GCODE_FILE_FILTER = "G-Code Files (*.gcode *.nc *.txt)"
SVG_FILE_FILTER = "SVG Files (*.svg)"
IMAGE_FILE_FILTER = "Raster Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)"
DEFAULT_PROJECT_EXTENSION = ".plotproj.json"

DEFAULT_PAGE_WIDTH_MM = 210.0
DEFAULT_PAGE_HEIGHT_MM = 210.0
DEFAULT_GRID_MM = 5.0

MIN_POINT_DISTANCE_MM = 0.02
DEFAULT_CURVE_FLATTEN_TOLERANCE_MM = 0.35
DEFAULT_JOIN_TOLERANCE_MM = 0.20

STYLE_SHEET = """
QMainWindow {
    background: #f4f6f8;
}
QToolBar {
    spacing: 6px;
    padding: 6px;
    background: #eaeef3;
    border: none;
}
QDockWidget::title {
    background: #e9edf2;
    padding: 6px 8px;
    font-weight: 600;
}
QGroupBox {
    border: 1px solid #cdd5df;
    border-radius: 6px;
    margin-top: 10px;
    background: white;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    padding: 6px 10px;
}
QTreeWidget, QListWidget, QTextEdit, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: white;
}
"""
