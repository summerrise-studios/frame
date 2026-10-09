"""Camera geometry: field of view, shot size from lens and distance, and projection.

Assumes a Super 35 sensor cropped to 16:9 (24.89 × 14.0 mm). Distances are in
metres, focal lengths in millimetres, and the floor plan is x/y with z up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SENSOR_W = 24.89
SENSOR_H = 14.0
ASPECT = SENSOR_W / SENSOR_H

# How much of a standing person's height fills the frame, by shot size (metres).
SIZES = {
    "ECU": 0.12,  # eyes, a detail
    "CU": 0.30,  # face
    "MCU": 0.50,  # head and chest
    "MS": 0.85,  # waist up
    "MLS": 1.30,  # knees up
    "FS": 2.10,  # whole body
    "LS": 4.50,  # body in its surroundings
    "ELS": 12.0,  # the place, people small
}
SIZE_ALIASES = {"WS": "LS", "WIDE": "LS", "EWS": "ELS", "XLS": "ELS", "XCU": "ECU", "BCU": "ECU",
                "MEDIUM": "MS", "CLOSE": "CU", "FULL": "FS", "COWBOY": "MLS", "MWS": "MLS"}
ORDER = list(SIZES)

# Default lens height (metres) for each camera angle.
ANGLE_HEIGHTS = {"eye": None, "high": 2.6, "low": 0.6, "overhead": 5.0, "dutch": None, "ground": 0.15}


def normalise_size(size: str) -> str | None:
    s = size.strip().upper().replace(".", "")
    s = SIZE_ALIASES.get(s, s)
    return s if s in SIZES else None


def hfov(lens_mm: float) -> float:
    """Horizontal field of view in degrees."""
    return math.degrees(2 * math.atan(SENSOR_W / (2 * lens_mm)))


def vfov(lens_mm: float) -> float:
    return math.degrees(2 * math.atan(SENSOR_H / (2 * lens_mm)))


def frame_height(distance_m: float, lens_mm: float) -> float:
    """Height of the slice of the world the frame covers at this distance."""
    return distance_m * SENSOR_H / lens_mm


def size_for(distance_m: float, lens_mm: float) -> str:
    h = frame_height(distance_m, lens_mm)
    return min(SIZES, key=lambda k: abs(math.log(h / SIZES[k])))


def size_gap(a: str, b: str) -> int:
    return abs(ORDER.index(a) - ORDER.index(b))


def distance_for(size: str, lens_mm: float) -> float:
    """How far the camera should be for this size on this lens."""
    return SIZES[size] * lens_mm / SENSOR_H


Vec = tuple[float, float, float]


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def distance(a: Vec, b: Vec) -> float:
    d = _sub(a, b)
    return math.sqrt(_dot(d, d))


@dataclass
class Camera:
    pos: Vec
    target: Vec
    lens: float
    roll: float = 0.0  # degrees, for dutch angles

    def __post_init__(self) -> None:
        f = _unit(_sub(self.target, self.pos))
        if abs(f[2]) > 0.999:  # looking straight down or up
            f = _unit((f[0] + 1e-3, f[1], f[2]))
        self.forward = f
        self.right = _unit(_cross(f, (0.0, 0.0, 1.0)))
        self.up = _cross(self.right, f)

    @property
    def yaw(self) -> float:
        """Compass direction the camera points, degrees from +x."""
        return math.degrees(math.atan2(self.forward[1], self.forward[0]))

    def depth(self, p: Vec) -> float:
        return _dot(_sub(p, self.pos), self.forward)

    def project(self, p: Vec) -> tuple[float, float] | None:
        """Frame position of a point: (-1, -1) bottom left to (1, 1) top right; None if behind."""
        v = _sub(p, self.pos)
        z = _dot(v, self.forward)
        if z <= 0.05:
            return None
        x = _dot(v, self.right) / z * self.lens / (SENSOR_W / 2)
        y = _dot(v, self.up) / z * self.lens / (SENSOR_H / 2)
        if self.roll:
            r = math.radians(self.roll)
            # rotate in frame units with the aspect taken into account
            xs, ys = x * ASPECT, y
            xs, ys = xs * math.cos(r) - ys * math.sin(r), xs * math.sin(r) + ys * math.cos(r)
            x, y = xs / ASPECT, ys
        return (x, y)

    def scale(self, size_m: float, p: Vec) -> float:
        """Width of an object of this size at p, as a fraction of the frame's half-width."""
        z = self.depth(p)
        return 0.0 if z <= 0.05 else size_m / z * self.lens / (SENSOR_W / 2)

    def clip_segment(self, a: Vec, b: Vec, near: float = 0.1) -> tuple[Vec, Vec] | None:
        """Trim a 3D segment to the part in front of the camera."""
        za, zb = self.depth(a), self.depth(b)
        if za < near and zb < near:
            return None
        if za < near or zb < near:
            t = (near - za) / (zb - za)
            m = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
            return (m, b) if za < near else (a, m)
        return (a, b)


def side_of_line(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """Signed distance of c from the line a→b on the floor plan (+ left, - right)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return (dx * (c[1] - a[1]) - dy * (c[0] - a[0])) / length
