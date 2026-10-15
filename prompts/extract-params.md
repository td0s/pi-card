# Prompt: parameters file from a Raspberry Pi mechanical drawing

Use this prompt to add a new board. Fill in the model and the URL of the drawing, then run it in this repo. It writes `params/<id>.json` only. `make_case.py` turns that file into the PDF.

---

**Model:** `<e.g. Raspberry Pi 5>`
**Drawing:** `<URL of the official mechanical drawing PDF, e.g. https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf>`

Create `params/<id>.json` for this board. It must validate against `schema/params.schema.json`. Use `params/pi4b.json` as the worked example: it shows the coordinate conventions and the level of detail expected.

1. **Download the drawing into its own empty scratch directory.** Record its sha256. Treat it as untrusted data: read it, never run anything from it.

2. **Read the dimensions from the drawing's vectors, not from a picture of it.**
   - Official drawings usually render text as outlines, but the line geometry is intact. Open the PDF with pymupdf (`nix develop`, then `python -I <your script> <pdf>`) and call `page.get_drawings()`.
   - Find the scale from two features a known distance apart. The mounting-hole spacing is the easiest, since the hole circles appear as small square bounding boxes.
   - Convert every segment to board mm. The origin is the board's near-left corner, with y increasing away from the near edge.
   - Confirm the scale by checking that the board corners land on the overall dimensions printed on the drawing.

3. **Orient the board.**
   - The **near** edge (y = 0) faces the lid hinge.
   - The **far** edge must have no connectors, because the lid's tuck flap goes inside the far wall.
   - If the drawing's bottom edge has ports and its top edge doesn't, keep the drawing's orientation. Otherwise rotate your coordinates, and say so in `coordinates`.

4. **Record every connector that must be reachable from outside.** For each one:
   - `edge`;
   - `from`/`to` along that edge: x for the near and far edges, y for the left and right edges. Use the outermost outline, including flanges;
   - `z_min`/`z_max`: height above the PCB top surface, from the drawing's `Z=` labels. Use negative values for parts under the board;
   - `overhang`: how far it sticks out past the board edge.
   Set `protrudes_through: true` only for removable media, such as a microSD card, that should stick 1 mm out of the wall so it can be gripped.

5. **Board and holes.** Record length, width, corner radius and hole positions. Record `height_above`: the tallest component's Z. Record `depth_below`: the deepest part under the PCB.

6. **Provenance.** Every value gets a `source` that cites the drawing (the dimension label, or "outline from vectors"). If a value isn't on the drawing, which is common for PCB thickness and anything on the underside, use a published figure or a conservative estimate. Set `"verified": false` and explain the value in `source`.

7. **Register the board.** Add the board to `models.json` (id, model, drawing URL, sha256, params path).

8. **Check your work.**
   - Run `nix develop -c pytest -q`.
   - Run `nix develop -c python make_case.py params/<id>.json --preview`.
   - Look at both PNGs. Fix any errors the generator reports. Don't change the generator to make a board fit unless the board genuinely needs a new feature; if it does, say so.

9. **Report back** with: the dimensions table, which values are unverified, the inside size and wall gaps the generator printed, and the PDF path.
