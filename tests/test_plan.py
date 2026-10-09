import copy
import json
from pathlib import Path

import pytest

from frame import cli, fountain, plan as plan_mod

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "last-train"
SCENE = fountain.load(EXAMPLE / "scene.fountain").scene(1)
DATA = json.loads((EXAMPLE / "shots.json").read_text(encoding="utf-8"))


def run(mutate=None):
    data = copy.deepcopy(DATA)
    if mutate:
        mutate(data)
    return plan_mod.check(plan_mod.build(data), SCENE)


def shot(p, sid):
    return next(s for s in p.shots if s.id == sid)


def test_example_plan_passes():
    p = run()
    assert p.ok and not p.warnings, [(s.id, s.problems, s.warnings) for s in p.shots] + p.errors + p.warnings


def test_crossing_the_line_is_caught():
    def cross(d):
        d["shots"][4]["camera"] = [0.5, 1.2, 1.5]  # shot 5, now north of the line
    s = shot(run(cross), "5")
    assert any("180-degree" in m for m in s.problems)


def test_intended_crossing_is_only_a_warning():
    def cross(d):
        d["shots"][4]["camera"] = [0.5, 1.2, 1.5]
        d["shots"][4]["crosses_line"] = True
    s = shot(run(cross), "5")
    assert not s.problems and any("intended" in m for m in s.warnings)


def test_subject_outside_the_frame():
    def narrow(d):
        d["shots"][3]["lens"] = 85  # the two-shot can't hold both people on an 85
    s = shot(run(narrow), "4")
    assert any("outside the frame" in m for m in s.problems)


def test_size_that_the_lens_cannot_give():
    def wrong(d):
        d["shots"][1]["size"] = "ECU"
    s = shot(run(wrong), "2")
    assert any("not a ECU" in m for m in s.warnings)


def test_jump_cut():
    def repeat(d):
        d["shots"].insert(5, dict(d["shots"][4], id="5B", beats=[5]))
    s = shot(run(repeat), "5B")
    assert any("jump cut" in m for m in s.warnings)


def test_uncovered_beat_and_unseen_speaker():
    def drop(d):
        d["shots"] = [s for s in d["shots"] if s["id"] not in ("8",)]
    p = run(drop)
    assert any(e.startswith("beat 8") for e in p.errors)


def test_character_not_entered_yet():
    def early(d):
        d["shots"][0]["subjects"] = ["ARJUN"]
    s = shot(run(early), "1")
    assert any("hasn't entered" in m for m in s.problems)


def test_unknown_values():
    def bad(d):
        d["shots"][0].update(size="HUGE", angle="sideways", lens=2)
        d["shots"][1]["subjects"] = ["NOBODY"]
        d["shots"][2]["beats"] = [99]
    p = run(bad)
    assert len(shot(p, "1").problems) == 3
    assert any("NOBODY" in m for m in shot(p, "2").problems)
    assert any("beat 99" in m for m in shot(p, "3").problems)


def test_blocking_follows_the_beats():
    p = run()
    assert p.mark("ARJUN", 2) is None
    assert p.mark("ARJUN", 5).height == pytest.approx(1.75)
    assert p.mark("ARJUN", 9).height == pytest.approx(1.2)


def test_cli_check_render_and_scene(tmp_path, capsys):
    script, shots = str(EXAMPLE / "scene.fountain"), str(EXAMPLE / "shots.json")
    assert cli.main(["check", script, shots]) == 0
    out = tmp_path / "previz.html"
    assert cli.main(["render", script, shots, "-o", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    assert page.count('class="panel"') == len(DATA["shots"]) and 'class="plan"' in page
    assert cli.main(["scene", script, "--json"]) == 0
    assert '"heading": "EXT. RAILWAY PLATFORM, WARANGAL - NIGHT"' in capsys.readouterr().out


def test_cli_check_fails_on_problems(tmp_path):
    data = copy.deepcopy(DATA)
    data["shots"][4]["camera"] = [0.5, 1.2, 1.5]
    bad = tmp_path / "shots.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["check", str(EXAMPLE / "scene.fountain"), str(bad)]) == 1
