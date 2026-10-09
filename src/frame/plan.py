"""A shot plan for one scene (shots.json) and the checks run on it.

See examples/last-train/shots.json for the format. In short:

* ``set``: props as boxes on the floor plan (metres; x/y centre, w/d/h size, z base).
* ``blocking``: where each character is, from which beat on, and how tall
  (1.7 standing, about 1.2 sitting).
* ``axis``: the two characters whose eyeline sets the 180-degree line.
* ``shots``: in cut order. Each has a camera position, a target, a lens, a
  size, the beats it covers and the subjects that must be in frame.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from . import optics
from .fountain import Scene

ANGLES = {"eye", "high", "low", "overhead", "dutch", "ground"}
MOVEMENTS = ("static", "pan", "tilt", "dolly", "track", "push", "pull", "handheld", "crane",
             "jib", "steadicam", "zoom", "whip", "follow", "arc")
STANDING = 1.7
EYE_DROP = 0.1  # eyes sit this far below the top of the head
DUTCH_ROLL = 12.0
JUMP_CUT_DEGREES = 30.0
DURATION_SLACK = 0.4  # shot durations may differ from the script estimate by ±40%


@dataclass
class Prop:
    name: str
    x: float
    y: float
    w: float = 0.5
    d: float = 0.5
    h: float = 1.0
    z: float = 0.0

    @property
    def top(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z + self.h)

    @property
    def centre(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z + self.h / 2)

    def corners(self) -> list[tuple[float, float, float]]:
        return [
            (self.x + sx * self.w / 2, self.y + sy * self.d / 2, self.z + sz * self.h)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (0, 1)
        ]


@dataclass
class Mark:
    beat: int
    x: float
    y: float
    height: float = STANDING

    @property
    def eye(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.height - EYE_DROP)


@dataclass
class Shot:
    id: str
    beats: list[int]
    size: str
    lens: float
    camera: tuple[float, float, float]
    target: tuple[float, float, float]
    target_name: str
    subjects: list[str]
    angle: str = "eye"
    movement: str = "static"
    duration: float = 0.0
    description: str = ""
    crosses_line: bool = False
    note: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    computed_size: str = ""

    @property
    def first_beat(self) -> int:
        return min(self.beats) if self.beats else 1

    @property
    def status(self) -> str:
        return "fix" if self.problems else "warn" if self.warnings else "ok"

    @property
    def cam(self) -> optics.Camera:
        return optics.Camera(self.camera, self.target, self.lens, DUTCH_ROLL if self.angle == "dutch" else 0.0)


@dataclass
class Plan:
    title: str
    scene: int
    props: dict[str, Prop]
    blocking: dict[str, list[Mark]]
    axis: list[str]
    shots: list[Shot]
    notes: str = ""
    errors: list[str] = field(default_factory=list)  # plan-level problems
    warnings: list[str] = field(default_factory=list)

    def mark(self, character: str, beat: int) -> Mark | None:
        """Where a character is at a beat; None if they haven't entered yet."""
        current = None
        for m in self.blocking.get(character, []):
            if m.beat <= beat:
                current = m
        return current

    def summary(self) -> dict:
        counts = {"ok": 0, "warn": 0, "fix": 0}
        for s in self.shots:
            counts[s.status] += 1
        return {"shots": len(self.shots), **counts, "plan_problems": len(self.errors)}

    @property
    def ok(self) -> bool:
        return not self.errors and all(not s.problems for s in self.shots)


def _marks(value) -> list[Mark]:
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], (int, float)):
        return [Mark(1, float(value[0]), float(value[1]))]
    if isinstance(value, dict):
        value = [value]
    marks = []
    for v in value:
        x, y = v["pos"]
        marks.append(Mark(int(v.get("beat", 1)), float(x), float(y), float(v.get("height", STANDING))))
    return sorted(marks, key=lambda m: m.beat)


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(data: dict) -> Plan:
    """Turn shots.json data into a Plan, resolving targets and camera heights."""
    props = {p["name"]: Prop(p["name"], float(p["x"]), float(p["y"]), float(p.get("w", 0.5)),
                             float(p.get("d", 0.5)), float(p.get("h", 1.0)), float(p.get("z", 0.0)))
             for p in data.get("set", {}).get("props", [])}
    blocking = {name.upper(): _marks(v) for name, v in data.get("blocking", {}).items()}
    plan = Plan(
        title=data.get("title", "Untitled"),
        scene=int(data.get("scene", 1)),
        props=props,
        blocking=blocking,
        axis=[a.upper() for a in data.get("axis", [])],
        shots=[],
        notes=data.get("notes", ""),
    )

    for i, s in enumerate(data.get("shots", []), 1):
        sid = str(s.get("id", i))
        beats = [int(b) for b in s.get("beats", [])]
        first = min(beats) if beats else 1
        problems: list[str] = []
        angle = str(s.get("angle", "eye")).lower()
        if angle not in ANGLES:
            problems.append(f"unknown angle \"{angle}\" (use one of {', '.join(sorted(ANGLES))})")
            angle = "eye"

        tgt = s.get("target")
        target_name = ""
        target: tuple[float, float, float] | None = None
        if isinstance(tgt, str):
            target_name = tgt.upper() if tgt.upper() in blocking else tgt
            if target_name in blocking:
                m = plan.mark(target_name, first)
                if m is None:
                    problems.append(f"target {target_name} hasn't entered by beat {first}")
                    m = blocking[target_name][0]
                target = m.eye
            elif tgt in props:
                target = props[tgt].top
            else:
                problems.append(f"target \"{tgt}\" is not a character in the blocking or a prop in the set")
        elif isinstance(tgt, (list, tuple)) and len(tgt) >= 2:
            target = (float(tgt[0]), float(tgt[1]), float(tgt[2]) if len(tgt) > 2 else 1.5)
        else:
            problems.append("no target: give a character, a prop, or [x, y, z]")
        if target is None:
            target = (0.0, 0.0, 1.5)

        cam = s.get("camera") or [0, -3]
        if len(cam) > 2:
            z = float(cam[2])
        else:
            z = optics.ANGLE_HEIGHTS.get(angle) or target[2]
        shot = Shot(
            id=sid,
            beats=beats,
            size=str(s.get("size", "")),
            lens=float(s.get("lens", 35)),
            camera=(float(cam[0]), float(cam[1]), z),
            target=target,
            target_name=target_name,
            subjects=[x.upper() if x.upper() in blocking else x for x in s.get("subjects", [])],
            angle=angle,
            movement=str(s.get("movement", "static")).lower(),
            duration=float(s.get("duration", 0)),
            description=s.get("description", ""),
            crosses_line=bool(s.get("crosses_line", False)),
            note=s.get("note", ""),
            problems=problems,
        )
        plan.shots.append(shot)
    return plan


def check(plan: Plan, scene: Scene) -> Plan:
    """Run every check, filling in each shot's problems and warnings."""
    n_beats = len(scene.beats)
    covered: dict[int, list[Shot]] = {}

    for shot in plan.shots:
        cam = shot.cam
        size = optics.normalise_size(shot.size)
        if size is None:
            shot.problems.append(f"unknown size \"{shot.size}\" (use one of {', '.join(optics.ORDER)})")
        if not 8 <= shot.lens <= 300:
            shot.problems.append(f"a {shot.lens:g} mm lens is outside the usual 8–300 mm range")
        if not shot.movement.startswith(MOVEMENTS):
            shot.warnings.append(f"unfamiliar camera move \"{shot.movement}\"")
        if not shot.beats:
            shot.problems.append("covers no beats")
        for b in shot.beats:
            if not 1 <= b <= n_beats:
                shot.problems.append(f"beat {b} doesn't exist (scene {scene.n} has {n_beats})")
            else:
                covered.setdefault(b, []).append(shot)
        if shot.duration <= 0:
            shot.warnings.append("no duration given")
        if optics.distance(shot.camera, shot.target) < 0.3:
            shot.problems.append("the camera is less than 30 cm from its target")

        # Everyone listed as a subject has to be in the frame.
        char_distances = []
        for name in shot.subjects:
            if name in plan.blocking:
                m = plan.mark(name, shot.first_beat)
                if m is None:
                    shot.problems.append(f"{name} hasn't entered by beat {shot.first_beat}")
                    continue
                point = m.eye
                char_distances.append(optics.distance(shot.camera, point))
            elif name in plan.props:
                point = plan.props[name].centre
            else:
                shot.problems.append(f"subject \"{name}\" is not in the blocking or the set")
                continue
            p = cam.project(point)
            if p is None:
                shot.problems.append(f"{name} is behind the camera")
            elif abs(p[0]) > 1.0 or abs(p[1]) > 1.0:
                where = "left" if p[0] < -1 else "right" if p[0] > 1 else "top" if p[1] > 1 else "bottom"
                shot.problems.append(f"{name} is outside the frame ({where} edge) on a {shot.lens:g} mm lens from here")

        # Does the lens and distance give the size the plan says?
        if shot.target_name in plan.blocking:
            ref = optics.distance(shot.camera, shot.target)
        elif char_distances:
            ref = sum(char_distances) / len(char_distances)
        else:
            ref = None
        if ref is not None:
            shot.computed_size = optics.size_for(ref, shot.lens)
            if size and optics.size_gap(size, shot.computed_size) > 1:
                want = optics.distance_for(size, shot.lens)
                shot.warnings.append(
                    f"at {ref:.1f} m a {shot.lens:g} mm lens frames {optics.frame_height(ref, shot.lens):.2f} m "
                    f"of height, a {shot.computed_size}, not a {size}. For a {size}, move to about {want:.1f} m "
                    f"or change the lens"
                )

    # 180-degree rule: cameras stay on one side of the line between the axis characters.
    if len(plan.axis) == 2:
        a, b = plan.axis
        if a not in plan.blocking or b not in plan.blocking:
            plan.errors.append(f"axis characters {a} and {b} must both be in the blocking")
        else:
            sides: list[tuple[Shot, float]] = []
            for shot in plan.shots:
                ma, mb = plan.mark(a, shot.first_beat), plan.mark(b, shot.first_beat)
                if ma is None or mb is None:
                    continue
                d = optics.side_of_line((ma.x, ma.y), (mb.x, mb.y), shot.camera[:2])
                if abs(d) >= 0.3:  # on (or near) the line counts as neutral
                    sides.append((shot, d))
            if sides:
                main = 1 if sum(1 if d > 0 else -1 for _, d in sides) >= 0 else -1
                for shot, d in sides:
                    if (d > 0) != (main > 0):
                        if shot.crosses_line:
                            shot.warnings.append("crosses the 180-degree line (marked as intended)")
                        else:
                            shot.problems.append(
                                f"crosses the 180-degree line between {a} and {b}: screen direction will flip. "
                                f"Move the camera to the other side, or set crosses_line with a reason"
                            )
    elif plan.axis:
        plan.errors.append("axis must name exactly two characters")

    # Jump cuts: the same framing again from almost the same place.
    for prev, shot in zip(plan.shots, plan.shots[1:]):
        if (
            prev.target_name
            and prev.target_name == shot.target_name
            and optics.normalise_size(prev.size) == optics.normalise_size(shot.size)
        ):
            turn = abs((prev.cam.yaw - shot.cam.yaw + 180) % 360 - 180)
            if turn < JUMP_CUT_DEGREES:
                shot.warnings.append(
                    f"cutting from shot {prev.id} to the same size on {shot.target_name} with only "
                    f"{turn:.0f}° of change may read as a jump cut; change the size or move 30° or more"
                )

    # Every beat is covered, and whoever speaks is seen speaking somewhere.
    for beat in scene.beats:
        shots = covered.get(beat.n, [])
        if not shots:
            plan.errors.append(f"beat {beat.n} isn't covered by any shot: {beat.text[:60]}")
        elif beat.kind == "dialogue" and not any(beat.character in s.subjects for s in shots):
            plan.warnings.append(
                f"beat {beat.n}: {beat.character} speaks but isn't a subject of any shot covering it "
                f"(fine if it's meant to play off-screen)"
            )

    total = sum(s.duration for s in plan.shots)
    est = scene.seconds
    if total and est and abs(total - est) > DURATION_SLACK * est:
        plan.warnings.append(
            f"shots add up to {total:g} s, but the script reads at about {est:g} s; check the pacing"
        )
    return plan


def fov_degrees(shot: Shot) -> float:
    return optics.hfov(shot.lens)


def yaw_radians(shot: Shot) -> float:
    return math.radians(shot.cam.yaw)
