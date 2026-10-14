# pi-card

Printable templates for fold-up card cases for Raspberry Pi boards.

Each template is a one-piece net. Cut it from card, fold it into a landscape tuck-top box, and bolt the Pi to its floor with M2.5 nylon screws on 5 mm spacers. The lid hinges along the near wall and its tuck flap goes inside the far wall. Every connector gets an opening placed from the official mechanical drawing.

## Build

```sh
nix develop
python make_case.py params/pi4b.json             # out/pi4b-case.pdf
python make_case.py params/pi4b.json --preview   # also PNGs of each page
python make_case.py params/pi4b.json --paper Letter --card 0.5 --no-doubler
pytest -q
```

The PDF's page 1 is the 1:1 template, with a 50 mm scale bar to check the print scale. Page 2 has the dimensions table, the assembly steps, the parts list and a section drawing. On Letter paper, the floor doubler moves to its own page.

## How it fits together

| Path | What it is |
| --- | --- |
| `params/<id>.json` | One board: outline, mounting holes, connectors and their heights, and where each value came from. Values not on the drawing are marked `"verified": false` and flagged in the PDF. |
| `schema/params.schema.json` | The schema every params file must match. |
| `models.json` | Registry of supported boards: drawing URL, the drawing's sha256 and the params file. |
| `make_case.py` | Deterministic generator: params in, PDF out. It refuses to write a PDF if any check fails. The checks are: the net fits the page, panels don't overlap, openings keep 2 mm of card from folds, screw holes are clear of folds, and the tuck flap doesn't cover a port. |
| `prompts/extract-params.md` | The prompt for adding a new board. It turns a mechanical drawing into a params file. |

## Design rules

- The board sits 5 mm above the floor. Wall height and every opening's height include the floor card, the spacer and the PCB.
- Inside height = spacer + PCB + tallest component + 3 mm.
- The gap between a board edge and its wall = that edge's largest connector overhang + 1 mm, and at least 2 mm. The exception is removable media such as microSD, which is set to stick 1 mm out through its wall.
- Each opening is the connector outline plus 1 mm on every side.
- The lid is the floor plus 2 × card thickness. The tuck flap is narrower than the far wall, so it clears the corner glue tabs.
- The printed side becomes the inside, so every fold is a valley fold.

## Boards

Newest first. None of these cases has been printed and folded yet.

| Board | Params | Source |
| --- | --- | --- |
| Raspberry Pi 5 | `params/pi5.json` | Official drawing, including its side view. Everything is verified. |
| Raspberry Pi Zero 2 W | `params/zero2w.json` | Positions come from the drawing. Heights, PCB thickness and the microSD card are unverified. |
| Raspberry Pi 4 Model B | `params/pi4b.json` | Positions and heights come from the drawing. PCB thickness and the microSD slot are unverified. |
| Raspberry Pi 3 Model A+ | `params/pi3aplus.json` | Positions and heights come from the drawing. Micro USB height, PCB thickness and the microSD slot are unverified. |
| Raspberry Pi 3 Model B+ | `params/pi3bplus.json` | Same as the 3A+. |
| Raspberry Pi Zero W | `params/zerow.json` | Positions and the microSD card come from the drawing. Heights and PCB thickness are unverified. |
| Raspberry Pi 3 Model B | `params/pi3b.json` | Same as the 3B+. |
| Raspberry Pi Zero | `params/zero.json` | Revision 1.2, with no camera connector. Use the Zero W case for revision 1.3. |
| Raspberry Pi 2 Model B | `params/pi2b.json` | No drawing is published, so it uses the B+ drawing. Everything is unverified. |
| Raspberry Pi 1 Model A+ | `params/aplus.json` | No drawing is published, so it uses the 3A+ drawing, as the docs advise. Everything is unverified. |
| Raspberry Pi 1 Model B+ | `params/bplus.json` | Same as the 3B+. |

Not covered:

- **Original Model A and B (2012–13):** no mechanical drawing is published. The board shape, mounting holes and connectors differ from later boards.
- **Pi 400, 500 and 500+:** these are keyboard computers.
- **Compute Modules:** they have no connectors of their own.
- **Pico:** this is a microcontroller board.

Build every board:

```sh
for p in params/*.json; do python make_case.py "$p"; done
```
