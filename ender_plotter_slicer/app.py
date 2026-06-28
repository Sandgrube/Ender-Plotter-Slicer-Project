from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import APP_NAME, APP_ORG, APP_VERSION, STYLE_SHEET
from .gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(STYLE_SHEET)

    window = MainWindow()
    window.show()
    return app.exec()
