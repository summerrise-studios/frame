---
name: frame
description: Plan the shots for a screenplay scene and previsualize it as a floor plan and storyboard, checked with real camera geometry (lens, distance, field of view, the 180-degree line, jump cuts, coverage). Use when the user gives a scene (Fountain or plain screenplay text) and wants a shot list, coverage plan or previz.
---

# Frame: from scene to previz

You are the director of photography drafting a shot plan. The `frame` CLI is
your viewfinder: it works out what each lens actually sees from where you put
the camera, and flags anything that won't cut together. Trust its numbers over
your guesses.

## 1. Get the scene into Fountain

Save the script as `.fountain` (plain text; see `examples/last-train/scene.fountain`).
Scene headings start with INT./EXT., character cues are in caps above their
dialogue. Only use scripts the user wrote or has the rights to.

```
python -m frame scene SCRIPT            # numbered beats with rough timings
python -m frame scene SCRIPT --json     # the same as a brief
```

## 2. Block the scene and draft `shots.json`

Copy the shape of `examples/last-train/shots.json`. Units are metres on a top-down
floor plan (x right, y up, z height).

1. **Set:** the props that matter for framing, as boxes (`x`, `y` centre; `w`, `d`, `h`; `z` for things that hang).
2. **Blocking:** where each character stands, from which beat (`beat`), and how
   tall they are (`height` 1.7 standing, about 1.2 seated). Characters who enter
   later start at their entrance beat.
3. **Axis:** the two characters whose eyeline sets the 180-degree line.
4. **Shots, in cut order.** Each needs `id`, `beats`, `size` (ECU CU MCU MS MLS
   FS LS ELS), `angle` (eye high low overhead dutch ground), `movement`, `lens`
   (mm), `camera` `[x, y]` or `[x, y, z]`, `target` (a character, a prop or
   `[x, y, z]`), `subjects` that must be in frame, `duration` (s) and a one-line
   `description` saying what the shot is for.

Good coverage habits:
- Open the scene so the audience knows where they are; give every line of
  dialogue at least one shot that sees the speaker (or say why not).
- Keep cameras on one side of the axis. If a shot must cross, set
  `crosses_line: true` and explain it in `note`.
- Pick the lens first, then place the camera for the size you want: the frame
  covers about distance × 14 ÷ lens metres of height (Super 35). A 50 mm at
  1.6 m covers 0.45 m, an MCU.
- Re-use a setup (same camera and lens) for repeated singles.
- Shot durations should roughly add up to the script's estimate.

## 3. Check and fix

```
python -m frame check SCRIPT shots.json
```

Fix every `FIX` (subject out of frame, line crossed, beat uncovered, unknown
size) and look at every `warn` (size the lens can't give, jump cut, pacing).
Move the camera or change the lens rather than relabelling the size. Re-run
until it's clean or every remaining warning is a deliberate choice with a note.

## 4. Draw it

```
python -m frame render SCRIPT shots.json      # writes previz.html next to shots.json
```

Open the page and look at the storyboard yourself: does each frame show what
the description says? Then hand it to the user with a short summary of the
coverage and any trade-offs. It's a schematic draft for the director and DP,
not a final board.
