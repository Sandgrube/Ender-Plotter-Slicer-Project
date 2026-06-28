from __future__ import annotations

from dataclasses import dataclass

from .document import PlotterDocument, TextObject
from .geometry import BoundingBox, combine_polylines_bbox


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    message: str
    object_id: str | None = None

    def as_text(self) -> str:
        prefix = self.severity.upper()
        return f"[{prefix}] {self.message}"


def validate_document(document: PlotterDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not document.objects:
        issues.append(ValidationIssue("error", "The project contains no objects."))
        return issues

    profile = document.profile
    if profile.pen_down_z_mm >= profile.pen_up_z_mm:
        issues.append(ValidationIssue("error", "Pen-down Z must be lower than pen-up Z."))
    if profile.pen_up_z_mm > profile.retract_z_mm:
        issues.append(ValidationIssue("warning", "Retract Z should normally be above pen-up Z."))

    available_width = profile.work_area_width_mm - 2.0 * profile.safety_margin_mm
    available_height = profile.work_area_height_mm - 2.0 * profile.safety_margin_mm
    if document.page.width_mm > available_width or document.page.height_mm > available_height:
        issues.append(
            ValidationIssue(
                "warning",
                "The page is larger than the profile's safe work area. Objects may plot outside the intended machine range.",
            )
        )

    plotable_count = 0
    page_box = document.page_bbox()
    for obj in document.visible_objects():
        if isinstance(obj, TextObject) and not obj.text.strip():
            issues.append(ValidationIssue("warning", f"Text object '{obj.name}' is empty.", obj.id))
        world_polylines = obj.world_polylines()
        if not world_polylines:
            issues.append(ValidationIssue("warning", f"Object '{obj.name}' has no plot-capable geometry.", obj.id))
            continue
        plotable_count += 1
        bbox = combine_polylines_bbox(world_polylines)
        if bbox is None:
            continue
        outside = (
            bbox.min_x < 0.0
            or bbox.min_y < 0.0
            or bbox.max_x > page_box.max_x
            or bbox.max_y > page_box.max_y
        )
        if outside:
            issues.append(
                ValidationIssue(
                    "warning",
                    f"Object '{obj.name}' extends outside the page boundary.",
                    obj.id,
                )
            )

    if plotable_count == 0:
        issues.append(ValidationIssue("error", "No visible object contains plot-capable geometry."))

    return issues
