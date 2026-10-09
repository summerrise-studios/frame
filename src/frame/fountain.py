"""Read screenplays written in Fountain (https://fountain.io), the plain-text screenplay format.

Covers the parts a shot list needs: title page, scene headings, action,
characters, parentheticals and dialogue. Notes ``[[...]]``, boneyard
``/* ... */``, sections ``#`` and synopses ``=`` are dropped. Each action
paragraph and each speech becomes one numbered beat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^(?:\.(?=[^.])|(?:INT|EXT|EST|INT\.?/EXT|I/E)[. ])", re.IGNORECASE)
TRANSITION = re.compile(r"^(?:>(?!.*<\s*$).*|[A-Z\s]+TO:)$")
CHARACTER = re.compile(r"^@?[^a-z]*[A-Z][^a-z]*$")  # all caps, extensions in () allowed
TITLE_KEY = re.compile(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$")

# Rough reading speeds for estimating screen time.
SPEECH_WPS = 2.5  # about 150 words a minute
ACTION_WPS = 3.0
MIN_ACTION_SECONDS = 2.0


@dataclass
class Beat:
    n: int
    kind: str  # "action" or "dialogue"
    text: str
    character: str = ""
    parenthetical: str = ""

    @property
    def seconds(self) -> float:
        words = len(self.text.split())
        if self.kind == "dialogue":
            s = words / SPEECH_WPS + 0.5
        else:
            s = max(MIN_ACTION_SECONDS, words / ACTION_WPS)
        return round(s * 2) / 2


@dataclass
class Scene:
    n: int
    heading: str
    beats: list[Beat] = field(default_factory=list)

    @property
    def characters(self) -> list[str]:
        seen: list[str] = []
        for b in self.beats:
            if b.character and b.character not in seen:
                seen.append(b.character)
        return seen

    @property
    def seconds(self) -> float:
        return sum(b.seconds for b in self.beats)

    def beat(self, n: int) -> Beat | None:
        return self.beats[n - 1] if 1 <= n <= len(self.beats) else None


@dataclass
class Script:
    title: str
    meta: dict[str, str]
    scenes: list[Scene]

    def scene(self, n: int) -> Scene:
        for s in self.scenes:
            if s.n == n:
                return s
        raise KeyError(f"no scene {n}; the script has scenes {[s.n for s in self.scenes]}")


def character_name(cue: str) -> str:
    cue = cue.lstrip("@").rstrip("^").strip()
    return re.sub(r"\s*\(.*?\)\s*", " ", cue).strip()


def parse(text: str) -> Script:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.DOTALL)
    paragraphs = [p.split("\n") for p in re.split(r"\n\s*\n", text.strip())]

    meta: dict[str, str] = {}
    if paragraphs and TITLE_KEY.match(paragraphs[0][0]) and not HEADING.match(paragraphs[0][0]):
        key = None
        for line in paragraphs.pop(0):
            if m := TITLE_KEY.match(line):
                key = m.group(1).strip().lower()
                meta[key] = m.group(2).strip()
            elif key:
                meta[key] = (meta[key] + " " + line.strip()).strip()

    scenes: list[Scene] = []
    scene: Scene | None = None

    def add(beat_kind: str, body: str, character: str = "", parenthetical: str = "") -> None:
        nonlocal scene
        if scene is None:
            scene = Scene(n=0, heading="(before the first scene heading)")
            scenes.append(scene)
        scene.beats.append(Beat(len(scene.beats) + 1, beat_kind, body, character, parenthetical))

    for para in paragraphs:
        lines = [l.rstrip() for l in para if l.strip() and not l.lstrip().startswith(("#", "="))]
        if not lines:
            continue
        first = lines[0].strip()
        if HEADING.match(first):
            heading = first[1:] if first.startswith(".") else first
            heading = re.sub(r"\s*#[^#]+#\s*$", "", heading).strip()  # scene numbers
            scene = Scene(n=len([s for s in scenes if s.n]) + 1, heading=heading.upper())
            scenes.append(scene)
            lines = lines[1:]
            if not lines:
                continue
            first = lines[0].strip()
        if len(lines) == 1 and TRANSITION.match(first):
            continue
        if len(lines) >= 2 and (first.startswith("@") or CHARACTER.match(first)) and not first.startswith("!"):
            parens = [l.strip() for l in lines[1:] if l.strip().startswith("(")]
            speech = [l.strip() for l in lines[1:] if not l.strip().startswith("(")]
            add("dialogue", " ".join(speech), character_name(first), " ".join(parens))
            continue
        body = " ".join(l.strip().lstrip("!").strip("><").strip() for l in lines)
        add("action", body)

    if scenes and scenes[0].n == 0 and not scenes[0].beats:
        scenes.pop(0)
    return Script(title=meta.get("title", "Untitled"), meta=meta, scenes=scenes)


def load(path: str | Path) -> Script:
    return parse(Path(path).read_text(encoding="utf-8"))


def brief(script: Script, scene_n: int | None = None) -> dict:
    """What a shot planner (human or Claude) works from, as plain data."""
    scenes = [script.scene(scene_n)] if scene_n is not None else script.scenes
    return {
        "title": script.title,
        "scenes": [
            {
                "scene": s.n,
                "heading": s.heading,
                "characters": s.characters,
                "estimated_seconds": s.seconds,
                "beats": [
                    {
                        "beat": b.n,
                        "kind": b.kind,
                        **({"character": b.character} if b.character else {}),
                        **({"parenthetical": b.parenthetical} if b.parenthetical else {}),
                        "text": b.text,
                        "seconds": b.seconds,
                    }
                    for b in s.beats
                ],
            }
            for s in scenes
        ],
    }
