# ELEGOO Neptune 2 Plotter Setup

This profile targets a Neptune-2/Ender-3-style Cartesian printer running Marlin-compatible firmware.

## Mechanical assumptions

- A pen holder is mounted to the toolhead.
- Pen pressure is controlled by the Z axis.
- The paper is fixed to the bed without clips protruding into the drawing area.
- The usable XY area is treated as 220 × 220 mm.

## Recommended first test

1. Remove the pen.
2. Export a tiny 20 × 20 mm square.
3. Run the G-code and verify the motion path.
4. Insert the pen.
5. Raise `Pen-down Z` if the pressure is too high.
6. Lower `Pen-down Z` if the line is too faint or broken.

## Profile defaults

```text
Work area:    220 × 220 mm
Page size:    210 × 210 mm
Pen up Z:     4.5 mm
Pen down Z:   0.2 mm
Travel speed: 3600 mm/min
Plot speed:   1200 mm/min
Z speed:      500 mm/min
```

These are conservative starting values, not universal final calibration values.
