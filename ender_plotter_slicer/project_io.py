from __future__ import annotations

from pathlib import Path
import json

from .document import PlotterDocument


class ProjectIOError(RuntimeError):
    pass


def save_project(document: PlotterDocument, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = document.to_dict()
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
    except Exception as exc:
        raise ProjectIOError(f"Could not save project to '{path}': {exc}") from exc


def load_project(path: str | Path) -> PlotterDocument:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise ProjectIOError(f"Could not read project file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ProjectIOError("Invalid project file: root element must be a JSON object.")

    try:
        document = PlotterDocument.from_dict(data)
        document.file_path = str(path)
        return document
    except Exception as exc:
        raise ProjectIOError(f"Project file '{path}' is not valid: {exc}") from exc
