"""frame command line: read a scene, check a shot plan, draw the previz."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fountain, plan as plan_mod, render


def _print_scene(script: fountain.Script, scene_n: int | None) -> None:
    print(script.title)
    for scene in script.scenes:
        if scene_n is not None and scene.n != scene_n:
            continue
        print(f"\nScene {scene.n}: {scene.heading}  (~{scene.seconds:g} s)")
        print(f"Characters: {', '.join(scene.characters) or '-'}")
        for b in scene.beats:
            parts = [f"{b.character}:" if b.character else "", b.parenthetical, b.text]
            print(f"  {b.n:>3}. [{b.seconds:g}s] " + " ".join(p for p in parts if p))


def _print_check(p: plan_mod.Plan) -> None:
    for s in p.shots:
        mark = {"ok": "ok  ", "warn": "warn", "fix": "FIX "}[s.status]
        size = s.size + (f" (lens gives {s.computed_size})" if s.computed_size and s.computed_size != s.size else "")
        print(f"{mark} shot {s.id}: {size}, {s.lens:g} mm, beats {', '.join(map(str, s.beats))}")
        for m in s.problems:
            print(f"        - {m}")
        for m in s.warnings:
            print(f"        ~ {m}")
    for e in p.errors:
        print(f"FIX  scene: {e}")
    for w in p.warnings:
        print(f"warn scene: {w}")
    s = p.summary()
    print(f"\n{s['ok']} ok, {s['warn']} to check, {s['fix']} to fix, {s['plan_problems']} scene problems")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="frame", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scene", help="list a script's scenes and numbered beats")
    sc.add_argument("script", type=Path)
    sc.add_argument("-s", "--scene", type=int)
    sc.add_argument("--json", action="store_true", help="print the planning brief as JSON")

    ck = sub.add_parser("check", help="check a shot plan against its scene")
    ck.add_argument("script", type=Path)
    ck.add_argument("shots", type=Path)

    rd = sub.add_parser("render", help="draw the floor plan and storyboard as HTML")
    rd.add_argument("script", type=Path)
    rd.add_argument("shots", type=Path)
    rd.add_argument("-o", "--output", type=Path, help="default: next to shots.json as previz.html")

    args = ap.parse_args(argv)
    script = fountain.load(args.script)

    if args.cmd == "scene":
        if args.json:
            print(json.dumps(fountain.brief(script, args.scene), ensure_ascii=False, indent=2))
        else:
            _print_scene(script, args.scene)
        return 0

    p = plan_mod.build(plan_mod.load(args.shots))
    plan_mod.check(p, script.scene(p.scene))
    if args.cmd == "check":
        _print_check(p)
        return 0 if p.ok else 1

    out = args.output or args.shots.with_name("previz.html")
    out.write_text(render.page(p, script.scene(p.scene)), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
