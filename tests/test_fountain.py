from frame.fountain import parse

SCRIPT = """Title: Test Script
Author: Someone

INT. KITCHEN - DAY

Steam rises from a pot.

MEERA (V.O.)
(quietly)
It's ready.

/* a cut idea */
RAVI
Already? [[check this line]]

CUT TO:

.FLASHBACK

Rain.

EXT. ROOF - NIGHT #2#

@McCLANE
Yippee.
"""


def test_title_page_and_scenes():
    s = parse(SCRIPT)
    assert s.title == "Test Script"
    assert [sc.heading for sc in s.scenes] == ["INT. KITCHEN - DAY", "FLASHBACK", "EXT. ROOF - NIGHT"]
    assert [sc.n for sc in s.scenes] == [1, 2, 3]


def test_beats_dialogue_and_parentheticals():
    scene = parse(SCRIPT).scene(1)
    kinds = [(b.kind, b.character) for b in scene.beats]
    assert kinds == [("action", ""), ("dialogue", "MEERA"), ("dialogue", "RAVI")]
    assert scene.beats[1].parenthetical == "(quietly)"
    assert scene.beats[1].text == "It's ready."
    assert scene.characters == ["MEERA", "RAVI"]


def test_notes_boneyard_and_transitions_are_dropped():
    scene = parse(SCRIPT).scene(1)
    assert "check this" not in scene.beats[2].text
    assert all("CUT TO" not in b.text for b in scene.beats)


def test_forced_character():
    assert parse(SCRIPT).scene(3).beats[0].character == "McCLANE"


def test_timing_estimate():
    beat = parse(SCRIPT).scene(1).beats[1]
    assert beat.seconds == 1.5  # 2 words at 2.5 words/s + 0.5 s, rounded to 0.5
    assert parse(SCRIPT).scene(2).beats[0].seconds == 2.0  # short action has a floor
