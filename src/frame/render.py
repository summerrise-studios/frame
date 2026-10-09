"""Draw a checked plan as one self-contained HTML page: floor plan, storyboard, notes."""

from __future__ import annotations

import html
import math

from . import optics
from .fountain import Scene
from .plan import Plan, Shot

PALETTE = ["#ff7445", "#5aa9e6", "#9bd17a", "#e6c25a", "#c48de6", "#e67a9b"]
STATUS = {"ok": ("fits", "#9bd17a"), "warn": ("check", "#e6c25a"), "fix": ("fix", "#ff6b6b")}
PANEL_W, PANEL_H = 320, 180


def _e(s: object) -> str:
    return html.escape(str(s))


def _colours(plan: Plan) -> dict[str, str]:
    return {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(plan.blocking)}


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def floor_plan(plan: Plan, width: int = 640) -> str:
    xs, ys = [], []
    for p in plan.props.values():
        xs += [p.x - p.w / 2, p.x + p.w / 2]
        ys += [p.y - p.d / 2, p.y + p.d / 2]
    for marks in plan.blocking.values():
        xs += [m.x for m in marks]
        ys += [m.y for m in marks]
    for s in plan.shots:
        xs.append(s.camera[0])
        ys.append(s.camera[1])
    if not xs:
        return ""
    pad = 1.0
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    scale = width / (x1 - x0)
    height = int((y1 - y0) * scale)

    def XY(x: float, y: float) -> tuple[float, float]:
        return ((x - x0) * scale, (y1 - y) * scale)

    def P(x: float, y: float) -> str:
        px, py = XY(x, y)
        return f"{px:.1f},{py:.1f}"

    def line(a: tuple[float, float], b: tuple[float, float], cls: str, style: str = "") -> str:
        (ax, ay), (bx, by) = XY(*a), XY(*b)
        st = f' style="{style}"' if style else ""
        return f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" class="{cls}"{st}/>'

    out = [f'<svg class="plan" viewBox="0 0 {width} {height}" role="img" aria-label="Floor plan">']
    # 1 m grid
    for gx in range(math.ceil(x0), math.floor(x1) + 1):
        out.append(line((gx, y0), (gx, y1), "grid"))
    for gy in range(math.ceil(y0), math.floor(y1) + 1):
        out.append(line((x0, gy), (x1, gy), "grid"))
    for p in plan.props.values():
        out.append(
            f'<rect x="{(p.x - p.w / 2 - x0) * scale:.1f}" y="{(y1 - p.y - p.d / 2) * scale:.1f}" '
            f'width="{p.w * scale:.1f}" height="{p.d * scale:.1f}" class="prop"/>'
            f'<text x="{(p.x - x0) * scale:.1f}" y="{(y1 - p.y) * scale + 4:.1f}" class="prop-label">{_e(p.name)}</text>'
        )
    if len(plan.axis) == 2 and all(a in plan.blocking for a in plan.axis):
        a, b = (plan.blocking[n][-1] for n in plan.axis)
        dx, dy = b.x - a.x, b.y - a.y
        n = math.hypot(dx, dy) or 1
        ext = 30
        out.append(line((a.x - dx / n * ext, a.y - dy / n * ext), (b.x + dx / n * ext, b.y + dy / n * ext), "axis"))
    for shot in plan.shots:
        cam = shot.cam
        reach = max(1.0, min(optics.distance(shot.camera, shot.target) * 1.1, 8.0))
        half = math.radians(optics.hfov(shot.lens) / 2)
        yaw = math.radians(cam.yaw)
        cx, cy = shot.camera[0], shot.camera[1]
        left = (cx + reach * math.cos(yaw + half), cy + reach * math.sin(yaw + half))
        right = (cx + reach * math.cos(yaw - half), cy + reach * math.sin(yaw - half))
        colour = STATUS[shot.status][1]
        out.append(f'<polygon points="{P(cx, cy)} {P(*left)} {P(*right)}" class="fov" '
                   f'style="fill:{colour};stroke:{colour}"><title>Shot {_e(shot.id)}</title></polygon>')
    colours = _colours(plan)
    for name, marks in plan.blocking.items():
        c = colours[name]
        for prev, m in zip(marks, marks[1:]):
            out.append(line((prev.x, prev.y), (m.x, m.y), "move", f"stroke:{c}"))
        for i, m in enumerate(marks):
            last = i == len(marks) - 1
            px, py = XY(m.x, m.y)
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{9 if last else 6}" style="fill:{c};opacity:{1 if last else .45}"/>')
            if last:
                out.append(f'<text x="{px + 13:.1f}" y="{py + 4:.1f}" class="name" style="fill:{c}">{_e(name)}</text>')
            else:
                out.append(f'<text x="{px + 9:.1f}" y="{py - 7:.1f}" class="beat">b{m.beat}</text>')
    setups: dict[tuple[float, float], list[str]] = {}  # shots sharing a camera position share a label
    for shot in plan.shots:
        setups.setdefault((round(shot.camera[0], 1), round(shot.camera[1], 1)), []).append(shot.id)
    for (x, y), ids in setups.items():
        px, py = XY(x, y)
        out.append(f'<rect x="{px - 7:.1f}" y="{py - 5:.1f}" width="14" height="10" rx="2" class="cam"/>'
                   f'<text x="{px:.1f}" y="{py + 19:.1f}" class="cam-label">{_e(" / ".join(ids))}</text>')
    out.append(f'<text x="8" y="{height - 8}" class="scale">grid = 1 m</text></svg>')
    return "".join(out)


def panel(plan: Plan, shot: Shot) -> str:
    """A schematic storyboard frame, projected through the shot's lens."""
    cam = shot.cam

    def to_px(p: tuple[float, float]) -> tuple[float, float]:
        return ((p[0] + 1) / 2 * PANEL_W, (1 - p[1]) / 2 * PANEL_H)

    out = [f'<svg class="panel" viewBox="0 0 {PANEL_W} {PANEL_H}" role="img" aria-label="Shot {_e(shot.id)} frame">',
           f'<defs><clipPath id="clip-{_e(shot.id)}"><rect width="{PANEL_W}" height="{PANEL_H}"/></clipPath></defs>',
           f'<g clip-path="url(#clip-{_e(shot.id)})"><rect width="{PANEL_W}" height="{PANEL_H}" class="sky"/>']

    # Floor grid, 1 m apart, so depth reads.
    xs = [m.x for ms in plan.blocking.values() for m in ms] + [p.x for p in plan.props.values()]
    ys = [m.y for ms in plan.blocking.values() for m in ms] + [p.y for p in plan.props.values()]
    gx0, gx1 = math.floor(min(xs + [shot.camera[0]]) - 6), math.ceil(max(xs + [shot.camera[0]]) + 6)
    gy0, gy1 = math.floor(min(ys + [shot.camera[1]]) - 6), math.ceil(max(ys + [shot.camera[1]]) + 6)
    lines = [((x, gy0, 0.0), (x, gy1, 0.0)) for x in range(gx0, gx1 + 1)]
    lines += [((gx0, y, 0.0), (gx1, y, 0.0)) for y in range(gy0, gy1 + 1)]
    for a, b in lines:
        seg = cam.clip_segment(a, b)
        if not seg:
            continue
        pa, pb = cam.project(seg[0]), cam.project(seg[1])
        if pa and pb:
            (ax, ay), (bx, by) = to_px(pa), to_px(pb)
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" class="floor"/>')

    # Props and people, farthest first.
    things = []
    for p in plan.props.values():
        things.append((cam.depth(p.centre), "prop", p))
    colours = _colours(plan)
    for name in plan.blocking:
        m = plan.mark(name, shot.first_beat)
        if m is not None:
            things.append((cam.depth((m.x, m.y, m.height / 2)), "person", (name, m)))
    for depth, kind, obj in sorted(things, key=lambda t: -t[0]):
        if depth <= 0.2:
            continue
        if kind == "prop":
            pts = [cam.project(c) for c in obj.corners()]
            if any(p is None for p in pts):
                continue
            hull = _hull([to_px(p) for p in pts])
            out.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in hull) + '" class="box"/>')
            continue
        name, m = obj
        out.append(_person(cam, to_px, name, m, colours[name]))
    out.append("</g>")
    # Rule-of-thirds guides
    for i in (1, 2):
        out.append(f'<line x1="{PANEL_W * i / 3:.1f}" y1="0" x2="{PANEL_W * i / 3:.1f}" y2="{PANEL_H}" class="thirds"/>'
                   f'<line x1="0" y1="{PANEL_H * i / 3:.1f}" x2="{PANEL_W}" y2="{PANEL_H * i / 3:.1f}" class="thirds"/>')
    out.append("</svg>")
    return "".join(out)


def _person(cam, to_px, name: str, m, colour: str) -> str:
    """A simple figure (legs, torso, neck, head) built in 3D and projected."""
    rx, ry = cam.right[0], cam.right[1]
    h = m.height
    seated = h < 1.4
    shoulder_z = h - 0.27
    hip_z = h * (0.40 if seated else 0.52)

    def at(off: float, z: float):
        p = cam.project((m.x + rx * off, m.y + ry * off, z))
        return to_px(p) if p else None

    shapes = {
        "legs": [at(-0.16, hip_z), at(0.16, hip_z), at(0.12, 0.0), at(-0.12, 0.0)],
        "torso": [at(-0.21, shoulder_z), at(0.21, shoulder_z), at(0.17, hip_z), at(-0.17, hip_z)],
        "neck": [at(-0.05, h - 0.2), at(0.05, h - 0.2), at(0.05, shoulder_z), at(-0.05, shoulder_z)],
    }
    head = cam.project((m.x, m.y, h - 0.12))
    if head is None or any(pt is None for pts in shapes.values() for pt in pts):
        return ""
    hx, hy = to_px(head)
    r = cam.scale(0.105, (m.x, m.y, h - 0.12)) * PANEL_W / 2
    out = []
    for part, pts in shapes.items():
        shade = "filter:brightness(.7)" if part == "legs" else ""
        out.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                   + f'" class="body" style="fill:{colour};stroke:{colour};{shade}"/>')
    out.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{r:.1f}" class="head" style="fill:{colour}"/>')
    out.append(f'<text x="{hx:.1f}" y="{max(12.0, hy - r - 5):.1f}" class="who">{_e(name)}</text>')
    return "".join(out)


CSS = """
:root{--bg:#11100f;--card:#1b1a18;--ink:#f5f1ea;--muted:#9f9b94;--line:#2c2a27;--accent:#ff7445}
@media (prefers-color-scheme: light){:root{--bg:#f6f3ee;--card:#fff;--ink:#1b1a18;--muted:#6b665f;--line:#e2ddd5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 16px}.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;color:#11100f}
.summary{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--muted)}
.plan{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}
.grid{stroke:var(--line);stroke-width:1}.prop{fill:#5e5a53;opacity:.55}.prop-label{fill:var(--muted);font-size:11px;text-anchor:middle}
.axis{stroke:var(--accent);stroke-dasharray:6 6;stroke-width:1.5;opacity:.8}.fov{fill-opacity:.08;stroke-opacity:.5;stroke-width:1}
.move{stroke-dasharray:3 4;stroke-width:1.5}.name{font-size:13px;font-weight:700}.beat{fill:var(--muted);font-size:10px}
.cam{fill:var(--ink)}.cam-label{fill:var(--ink);font-size:11px;font-weight:700;text-anchor:middle}.scale{fill:var(--muted);font-size:11px}
.board{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.shot{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.panel{display:block;width:100%;height:auto;background:#24282d}.sky{fill:#2a2f35}.floor{stroke:#4b525b;stroke-width:1}
.box{fill:#6b655d;stroke:#8a837a;stroke-width:1}.body{stroke-width:2;stroke-linejoin:round}.head{stroke:#2a2f35;stroke-width:2}.who{fill:#fff;font-size:10px;text-anchor:middle;font-weight:600}
.thirds{stroke:#fff;stroke-opacity:.12}
.meta{padding:12px 14px}.meta h3{margin:0 0 4px;font-size:15px;display:flex;justify-content:space-between;gap:8px;align-items:center}
.spec{color:var(--muted);font-size:13px;margin:0 0 6px}.desc{margin:0 0 6px}
.msgs{margin:6px 0 0;padding-left:18px;font-size:13px}.msgs li.p{color:#ff8a8a}.msgs li.w{color:#e6c25a}
.notes li{margin-bottom:4px}footer{color:var(--muted);font-size:13px;margin-top:40px}
"""


def page(plan: Plan, scene: Scene) -> str:
    s = plan.summary()
    out = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        '<meta name=viewport content="width=device-width,initial-scale=1">',
        f"<title>{_e(plan.title)}: scene {plan.scene} previz</title><style>{CSS}</style></head><body><main>",
        f"<h1>{_e(plan.title)}</h1>",
        f'<p class="sub">Scene {scene.n} · {_e(scene.heading)} · script reads at about {scene.seconds:g} s · '
        f'shots add up to {sum(x.duration for x in plan.shots):g} s</p>',
        f'<div class="summary"><span>{s["shots"]} shots</span><span>{s["ok"]} fit</span>'
        f'<span>{s["warn"]} to check</span><span>{s["fix"]} to fix</span>'
        f'<span>{len(plan.errors)} scene problems</span></div>',
        "<h2>Floor plan</h2>",
        floor_plan(plan),
        '<p class="sub">Top view. Wedges are each shot\'s field of view; the dashed orange line is the '
        "180-degree line. Faded dots are earlier marks.</p>",
        '<h2>Storyboard</h2><div class="board">',
    ]
    for shot in plan.shots:
        label, colour = STATUS[shot.status]
        beats = ", ".join(str(b) for b in shot.beats)
        size = optics.normalise_size(shot.size) or shot.size
        computed = f" (lens gives {shot.computed_size})" if shot.computed_size and shot.computed_size != size else ""
        out.append(
            f'<article class="shot">{panel(plan, shot)}<div class="meta">'
            f'<h3><span>Shot {_e(shot.id)}</span><span class="pill" style="background:{colour}">{label}</span></h3>'
            f'<p class="spec">{_e(size)}{_e(computed)} · {_e(shot.angle)} · {_e(shot.movement)} · '
            f'{shot.lens:g} mm · {shot.duration:g} s · beats {beats}</p>'
            f'<p class="desc">{_e(shot.description)}</p>'
        )
        msgs = [("p", m) for m in shot.problems] + [("w", m) for m in shot.warnings]
        if shot.note:
            msgs.append(("", shot.note))
        if msgs:
            out.append('<ul class="msgs">' + "".join(f'<li class="{c}">{_e(m)}</li>' for c, m in msgs) + "</ul>")
        out.append("</div></article>")
    out.append("</div>")
    notes = [("p", e) for e in plan.errors] + [("w", w) for w in plan.warnings]
    if notes or plan.notes:
        out.append('<h2>Scene notes</h2><ul class="msgs notes">')
        out += [f'<li class="{c}">{_e(m)}</li>' for c, m in notes]
        if plan.notes:
            out.append(f"<li>{_e(plan.notes)}</li>")
        out.append("</ul>")
    out.append(
        "<h2>Script</h2><ol>"
        + "".join(
            f"<li><strong>{_e(b.character)}</strong> {_e(b.text)}</li>" if b.character else f"<li>{_e(b.text)}</li>"
            for b in scene.beats
        )
        + "</ol>"
    )
    out.append(
        '<footer>Schematic previz from <a href="https://github.com/summerrise-studios/frame" style="color:inherit">Frame</a> '
        "by Summer Rise Studios. Figures are drawn through each shot's lens on a Super 35 16:9 sensor; "
        "proportions are approximate.</footer></main></body></html>"
    )
    return "".join(out)
