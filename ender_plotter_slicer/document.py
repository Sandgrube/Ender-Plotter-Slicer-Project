from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .config import (
    DEFAULT_CURVE_FLATTEN_TOLERANCE_MM,
    DEFAULT_GRID_MM,
    DEFAULT_JOIN_TOLERANCE_MM,
    DEFAULT_PAGE_HEIGHT_MM,
    DEFAULT_PAGE_WIDTH_MM,
)
from .geometry import BoundingBox, Polyline, combine_polylines_bbox, transform_for_object
from .profiles import MachineProfile, builtin_profiles


def new_object_id() -> str:
    return uuid4().hex[:12]


@dataclass(slots=True)
class PageSettings:
    width_mm: float = DEFAULT_PAGE_WIDTH_MM
    height_mm: float = DEFAULT_PAGE_HEIGHT_MM
    grid_mm: float = DEFAULT_GRID_MM
    show_grid: bool = True
    snap_enabled: bool = False


@dataclass(slots=True)
class GCodeSettings:
    optimize_order: bool = True
    curve_tolerance_mm: float = DEFAULT_CURVE_FLATTEN_TOLERANCE_MM
    join_tolerance_mm: float = DEFAULT_JOIN_TOLERANCE_MM
    include_comments: bool = True
    keep_pen_down_on_touching_paths: bool = True


@dataclass(slots=True)
class DocumentObject:
    id: str = field(default_factory=new_object_id)
    name: str = "Object"
    object_type: str = "geometry"
    x_mm: float = 0.0
    y_mm: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    z_order: int = 0
    visible: bool = True
    locked: bool = False
    local_polylines: list[Polyline] = field(default_factory=list)

    def transform(self):
        return transform_for_object(self.x_mm, self.y_mm, self.scale_x, self.scale_y, self.rotation_deg)

    def world_polylines(self) -> list[Polyline]:
        transform = self.transform()
        return [polyline.transformed(transform) for polyline in self.local_polylines]

    def world_bbox(self) -> BoundingBox | None:
        return combine_polylines_bbox(self.world_polylines())

    def base_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "object_type": self.object_type,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation_deg": self.rotation_deg,
            "z_order": self.z_order,
            "visible": self.visible,
            "locked": self.locked,
            "local_polylines": [polyline.as_serializable() for polyline in self.local_polylines],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.base_dict()

    def clone(self) -> "DocumentObject":
        data = self.to_dict()
        data["id"] = new_object_id()
        data["name"] = f"{self.name} Copy"
        return object_from_dict(data)


@dataclass(slots=True)
class SvgObject(DocumentObject):
    object_type: str = "svg"
    source_path: str = ""
    source_name: str = ""
    import_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = self.base_dict()
        data.update(
            {
                "source_path": self.source_path,
                "source_name": self.source_name,
                "import_notes": self.import_notes,
            }
        )
        return data


@dataclass(slots=True)
class RasterObject(DocumentObject):
    object_type: str = "raster"
    source_path: str = ""
    source_name: str = ""
    import_notes: str = ""
    sampled_columns: int = 0
    sampled_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = self.base_dict()
        data.update(
            {
                "source_path": self.source_path,
                "source_name": self.source_name,
                "import_notes": self.import_notes,
                "sampled_columns": self.sampled_columns,
                "sampled_rows": self.sampled_rows,
            }
        )
        return data


@dataclass(slots=True)
class TextObject(DocumentObject):
    object_type: str = "text"
    text: str = "Text"
    font_family: str = "DejaVu Sans"
    font_size_mm: float = 12.0
    letter_spacing_mm: float = 0.0
    line_spacing: float = 1.2

    def rebuild_geometry(self) -> None:
        from .text_path import text_to_polylines

        self.local_polylines = text_to_polylines(
            text=self.text,
            font_family=self.font_family,
            font_size_mm=self.font_size_mm,
            letter_spacing_mm=self.letter_spacing_mm,
            line_spacing=self.line_spacing,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.base_dict()
        data.update(
            {
                "text": self.text,
                "font_family": self.font_family,
                "font_size_mm": self.font_size_mm,
                "letter_spacing_mm": self.letter_spacing_mm,
                "line_spacing": self.line_spacing,
            }
        )
        return data


def object_from_dict(data: dict[str, Any]) -> DocumentObject:
    object_type = data.get("object_type", "geometry")
    common = dict(
        id=data.get("id", new_object_id()),
        name=data.get("name", "Object"),
        x_mm=float(data.get("x_mm", 0.0)),
        y_mm=float(data.get("y_mm", 0.0)),
        scale_x=float(data.get("scale_x", 1.0)),
        scale_y=float(data.get("scale_y", 1.0)),
        rotation_deg=float(data.get("rotation_deg", 0.0)),
        z_order=int(data.get("z_order", 0)),
        visible=bool(data.get("visible", True)),
        locked=bool(data.get("locked", False)),
        local_polylines=[Polyline.from_serializable(item) for item in data.get("local_polylines", [])],
    )
    if object_type == "text":
        obj = TextObject(
            **common,
            text=data.get("text", ""),
            font_family=data.get("font_family", "DejaVu Sans"),
            font_size_mm=float(data.get("font_size_mm", 12.0)),
            letter_spacing_mm=float(data.get("letter_spacing_mm", 0.0)),
            line_spacing=float(data.get("line_spacing", 1.2)),
        )
        if not obj.local_polylines:
            obj.rebuild_geometry()
        return obj
    if object_type == "svg":
        return SvgObject(
            **common,
            source_path=data.get("source_path", ""),
            source_name=data.get("source_name", ""),
            import_notes=data.get("import_notes", ""),
        )
    if object_type == "raster":
        return RasterObject(
            **common,
            source_path=data.get("source_path", ""),
            source_name=data.get("source_name", ""),
            import_notes=data.get("import_notes", ""),
            sampled_columns=int(data.get("sampled_columns", 0)),
            sampled_rows=int(data.get("sampled_rows", 0)),
        )
    return DocumentObject(**common)


@dataclass(slots=True)
class PlotterDocument:
    project_name: str = "Untitled Project"
    page: PageSettings = field(default_factory=PageSettings)
    gcode: GCodeSettings = field(default_factory=GCodeSettings)
    profile: MachineProfile = field(default_factory=lambda: builtin_profiles()["ELEGOO Neptune 2 Pen Plotter"])
    objects: list[DocumentObject] = field(default_factory=list)
    file_path: str | None = None
    selected_ids: list[str] = field(default_factory=list)
    canvas_state: dict[str, Any] = field(default_factory=lambda: {"zoom": 1.0})

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "project_name": self.project_name,
            "page": asdict(self.page),
            "gcode": asdict(self.gcode),
            "profile": self.profile.to_dict(),
            "objects": [obj.to_dict() for obj in sorted(self.objects, key=lambda item: item.z_order)],
            "selected_ids": list(self.selected_ids),
            "canvas_state": dict(self.canvas_state),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PlotterDocument":
        page = PageSettings(**data.get("page", {}))
        gcode = GCodeSettings(**data.get("gcode", {}))
        profile_data = data.get("profile", {})
        profile = MachineProfile.from_dict(profile_data) if profile_data else builtin_profiles()["ELEGOO Neptune 2 Pen Plotter"]
        objects = [object_from_dict(item) for item in data.get("objects", [])]
        doc = PlotterDocument(
            project_name=data.get("project_name", "Untitled Project"),
            page=page,
            gcode=gcode,
            profile=profile,
            objects=objects,
            selected_ids=list(data.get("selected_ids", [])),
            canvas_state=dict(data.get("canvas_state", {"zoom": 1.0})),
        )
        return doc

    def add_object(self, obj: DocumentObject) -> None:
        obj.z_order = len(self.objects)
        self.objects.append(obj)

    def remove_object_ids(self, object_ids: list[str]) -> None:
        self.objects = [obj for obj in self.objects if obj.id not in set(object_ids)]
        self.selected_ids = [obj_id for obj_id in self.selected_ids if obj_id not in set(object_ids)]
        self.reindex_z_order()

    def reindex_z_order(self) -> None:
        for index, obj in enumerate(sorted(self.objects, key=lambda item: item.z_order)):
            obj.z_order = index
        self.objects.sort(key=lambda item: item.z_order)

    def object_by_id(self, object_id: str) -> DocumentObject | None:
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    def selected_objects(self) -> list[DocumentObject]:
        lookup = set(self.selected_ids)
        return [obj for obj in self.objects if obj.id in lookup]

    def visible_objects(self) -> list[DocumentObject]:
        return [obj for obj in sorted(self.objects, key=lambda item: item.z_order) if obj.visible]

    def duplicate_selected(self) -> list[DocumentObject]:
        clones: list[DocumentObject] = []
        for obj in self.selected_objects():
            clone = obj.clone()
            clone.x_mm += 5.0
            clone.y_mm += 5.0
            self.add_object(clone)
            clones.append(clone)
        self.selected_ids = [obj.id for obj in clones]
        self.reindex_z_order()
        return clones

    def page_bbox(self) -> BoundingBox:
        return BoundingBox(0.0, 0.0, self.page.width_mm, self.page.height_mm)

    def set_profile(self, profile: MachineProfile) -> None:
        self.profile = profile
