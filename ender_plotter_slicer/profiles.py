from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
import json


@dataclass(slots=True)
class MachineProfile:
    name: str
    work_area_width_mm: float
    work_area_height_mm: float
    work_offset_x_mm: float
    work_offset_y_mm: float
    origin_mode: str = "top_left"
    safe_start_x_mm: float = 5.0
    safe_start_y_mm: float = 5.0
    home_enabled: bool = True
    pen_up_z_mm: float = 5.0
    pen_down_z_mm: float = 0.0
    retract_z_mm: float = 8.0
    travel_feed_mm_min: float = 3000.0
    plot_feed_mm_min: float = 1200.0
    z_feed_mm_min: float = 600.0
    start_gcode: str = "G21\nG90"
    end_gcode: str = "M400"
    safety_margin_mm: float = 2.0
    mirror_x: bool = False
    mirror_y: bool = False
    swap_xy: bool = False
    output_rotation_deg: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "MachineProfile":
        return MachineProfile(**data)


def builtin_profiles() -> dict[str, MachineProfile]:
    neptune_pen = MachineProfile(
        name="ELEGOO Neptune 2 Pen Plotter",
        work_area_width_mm=220.0,
        work_area_height_mm=220.0,
        work_offset_x_mm=5.0,
        work_offset_y_mm=5.0,
        origin_mode="top_left",
        safe_start_x_mm=10.0,
        safe_start_y_mm=10.0,
        home_enabled=True,
        pen_up_z_mm=4.5,
        pen_down_z_mm=0.2,
        retract_z_mm=8.0,
        travel_feed_mm_min=3600.0,
        plot_feed_mm_min=1200.0,
        z_feed_mm_min=500.0,
        start_gcode="\n".join(
            [
                "G21 ; millimetres",
                "G90 ; absolute positioning",
                "M82 ; absolute extruder mode",
                "M104 S0 ; hotend off",
                "M140 S0 ; bed off",
                "M107 ; fan off",
            ]
        ),
        end_gcode="\n".join(
            [
                "M400 ; wait for moves",
                "G0 Z8 F500 ; pen fully raised",
                "G0 X10 Y10 F3600 ; park front-left",
                "M84 ; disable steppers",
            ]
        ),
        safety_margin_mm=5.0,
        mirror_x=False,
        mirror_y=False,
        swap_xy=False,
        output_rotation_deg=0.0,
    )

    ender_pen = MachineProfile(
        name="Ender 3 Pen Plotter",
        work_area_width_mm=220.0,
        work_area_height_mm=220.0,
        work_offset_x_mm=10.0,
        work_offset_y_mm=10.0,
        origin_mode="top_left",
        safe_start_x_mm=10.0,
        safe_start_y_mm=10.0,
        home_enabled=True,
        pen_up_z_mm=4.5,
        pen_down_z_mm=0.2,
        retract_z_mm=8.0,
        travel_feed_mm_min=3600.0,
        plot_feed_mm_min=1400.0,
        z_feed_mm_min=500.0,
        start_gcode="\n".join(
            [
                "G21 ; millimetres",
                "G90 ; absolute positioning",
                "M83 ; relative extruder mode, irrelevant but harmless on Marlin",
            ]
        ),
        end_gcode="\n".join(
            [
                "M400 ; wait for moves",
                "G0 X10 Y10 ; park near front-left",
            ]
        ),
        safety_margin_mm=3.0,
        mirror_x=False,
        mirror_y=False,
        swap_xy=False,
        output_rotation_deg=0.0,
    )
    landscape = MachineProfile(
        name="Ender 3 Pen Plotter Rotated Bed",
        work_area_width_mm=220.0,
        work_area_height_mm=220.0,
        work_offset_x_mm=10.0,
        work_offset_y_mm=10.0,
        origin_mode="top_left",
        safe_start_x_mm=10.0,
        safe_start_y_mm=10.0,
        home_enabled=True,
        pen_up_z_mm=4.5,
        pen_down_z_mm=0.2,
        retract_z_mm=8.0,
        travel_feed_mm_min=3600.0,
        plot_feed_mm_min=1400.0,
        z_feed_mm_min=500.0,
        start_gcode=ender_pen.start_gcode,
        end_gcode=ender_pen.end_gcode,
        safety_margin_mm=3.0,
        mirror_x=False,
        mirror_y=False,
        swap_xy=True,
        output_rotation_deg=0.0,
    )
    return {profile.name: profile for profile in [neptune_pen, ender_pen, landscape]}


def load_external_profiles(directory: str | Path) -> dict[str, MachineProfile]:
    directory = Path(directory)
    profiles: dict[str, MachineProfile] = {}
    if not directory.exists():
        return profiles
    for path in directory.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            profile = MachineProfile.from_dict(data)
            profiles[profile.name] = profile
        except Exception:
            continue
    return profiles


def profile_registry(profile_directory: str | Path | None = None) -> dict[str, MachineProfile]:
    registry = builtin_profiles()
    if profile_directory is not None:
        registry.update(load_external_profiles(profile_directory))
    return registry
