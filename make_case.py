#!/usr/bin/env python3
"""Generate a fold-up card case template (PDF) for a Raspberry Pi board.

The case is a landscape tuck-top box. The board is bolted to the floor on
5 mm spacers. The lid hinges on the near wall and its tuck flap goes inside
the far wall. All dimensions are in mm; the net is drawn at 1:1.

Net coordinates: the floor's near-left inside corner is the origin, x runs
along the board's long edge and y runs from the near wall to the far wall.
The printed side becomes the inside of the box, so every fold is a valley
fold seen from the printed side.
"""
import argparse
import datetime
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

VERSION = "0.1.0"
MM = 72 / 25.4  # PDF points per mm
PAGES = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4)}
SCHEMA = Path(__file__).with_name("schema") / "params.schema.json"

SPACER = 5.0          # spacer height between the floor and the bottom of the PCB
HEADROOM = 3.0        # gap between the tallest component and the lid
PORT_MARGIN = 1.0     # extra opening around each connector, per side
MIN_CLEARANCE = 2.0   # minimum gap between a board edge and its wall
FOLD_MIN = 2.0        # card left between an opening and a fold or wall end
HOLE_D = 2.8          # screw hole diameter (M2.5)
HOLE_EDGE_MIN = 3.0   # screw hole centre to floor fold
TAB_W = 8.0           # glue tab width
TAB_TAPER = 3.0       # glue tab taper at each end
DUST_DEPTH = 7.0      # dust flap depth, short of the tuck flap
NOTCH_R = 7.5         # thumb notch radius
TUCK_MAX = 15.0       # tuck flap depth limit
MARGIN = 10.0         # page margin
SCALE_BAR = 50.0


def load_params(path):
    params = json.loads(Path(path).read_text())
    jsonschema.validate(params, json.loads(SCHEMA.read_text()))
    return params


def val(m):
    return m["value"]


@dataclass
class Wall:
    name: str
    o: tuple       # net position of local (0, 0): the fold line's start
    eu: tuple      # unit vector along the fold line
    ez: tuple      # unit vector up the wall, away from the floor
    length: float
    offset: float  # u position of board coordinate 0 along this edge

    def pt(self, u, z):
        return (self.o[0] + u * self.eu[0] + z * self.ez[0],
                self.o[1] + u * self.eu[1] + z * self.ez[1])


@dataclass
class Panel:
    name: str
    pts: list
    label: str = ""
    angle: float = 0.0   # label direction, degrees
    glue: bool = False


@dataclass
class Opening:
    wall: str
    port: str
    label: str
    u0: float
    u1: float
    z0: float
    z1: float
    pts: list
    angle: float = 0.0


@dataclass
class Design:
    params: dict
    card: float
    paper: str
    doubler: bool
    dims: dict = field(default_factory=dict)
    clearance: dict = field(default_factory=dict)
    walls: dict = field(default_factory=dict)
    panels: list = field(default_factory=list)
    hinges: list = field(default_factory=list)
    openings: list = field(default_factory=list)
    tab_holes: list = field(default_factory=list)
    holes: list = field(default_factory=list)
    board_outline: list = field(default_factory=list)
    doubler_rect: tuple = None
    tab_attach: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def rect_pts(wall, u0, u1, z0, z1):
    return [wall.pt(u0, z0), wall.pt(u1, z0), wall.pt(u1, z1), wall.pt(u0, z1)]


def clearances(p, T, errors):
    """Gap between each board edge and its wall."""
    cl = {}
    for side in ("near", "far", "left", "right"):
        ports = [q for q in p["ports"] if q["edge"] == side]
        through = [q for q in ports if q.get("protrudes_through")]
        others = [q for q in ports if not q.get("protrudes_through")]
        need = max([MIN_CLEARANCE] + [q["overhang"] + 1 for q in others])
        if through:
            # Let these stick 1 mm out through the wall so they can be gripped.
            c = min(q["overhang"] - T - 1 for q in through)
            low = max([0.5] + [q["overhang"] + 1 for q in others])
            if c < low:
                errors.append(f"{side} edge: {', '.join(q['id'] for q in through)} "
                              f"can't protrude through the wall with clearance {c:.2f} mm")
                c = low
            cl[side] = c
        else:
            cl[side] = need
    return cl


def design(p, card=0.4, paper="A4", doubler=True):
    d = Design(params=p, card=card, paper=paper, doubler=doubler)
    T = card
    Lb, Wb = val(p["board"]["length"]), val(p["board"]["width"])
    pcb = val(p["board"]["thickness"])
    cl = d.clearance = clearances(p, T, d.errors)

    L = Lb + cl["left"] + cl["right"]
    W = Wb + cl["near"] + cl["far"]
    H_in = SPACER + pcb + val(p["height_above"]) + HEADROOM
    Hw = H_in + T
    board_z = T + SPACER + pcb   # PCB top surface above the floor fold line
    d.dims = dict(L=L, W=W, H_in=H_in, Hw=Hw, board_z=board_z,
                  lid_L=L + 2 * T, lid_W=W + 2 * T)

    if val(p["depth_below"]) + 0.5 > SPACER:
        d.errors.append(f"parts {val(p['depth_below'])} mm below the board need more than a {SPACER} mm spacer")

    walls = d.walls = {
        "near": Wall("near", (0, 0), (1, 0), (0, -1), L, cl["left"]),
        "far": Wall("far", (0, W), (1, 0), (0, 1), L, cl["left"]),
        "left": Wall("left", (0, 0), (0, 1), (-1, 0), W, cl["near"]),
        "right": Wall("right", (L, 0), (0, 1), (1, 0), W, cl["near"]),
    }

    # Floor, screw holes and the board's footprint
    d.panels.append(Panel("floor", [(0, 0), (L, 0), (L, W), (0, W)], "FLOOR (printed side is the inside)"))
    for hx, hy in p["holes"]["positions"]:
        d.holes.append((cl["left"] + hx, cl["near"] + hy))
    d.board_outline = [(cl["left"], cl["near"]), (cl["left"] + Lb, cl["near"]),
                       (cl["left"] + Lb, cl["near"] + Wb), (cl["left"], cl["near"] + Wb)]
    d.hinges.extend(edges(d.panels[0].pts))

    # Walls. The far wall has the thumb notch in its top edge.
    labels = {"near": "NEAR WALL (lid hinge)", "far": "FAR WALL (tuck goes inside)",
              "left": "LEFT END", "right": "RIGHT END"}
    for name, w in walls.items():
        local = [(0, 0), (w.length, 0), (w.length, Hw)]
        if name == "far":
            c = w.length / 2
            for i in range(25):
                a = -math.pi * i / 24
                local.append((c + NOTCH_R * math.cos(a), Hw + NOTCH_R * math.sin(a)))
        local.append((0, Hw))
        d.panels.append(Panel(name, [w.pt(u, z) for u, z in local], labels[name],
                              math.degrees(math.atan2(w.eu[1], w.eu[0]))))

    # Port openings
    for q in p["ports"]:
        w = walls[q["edge"]]
        u0, u1 = w.offset + q["from"] - PORT_MARGIN, w.offset + q["to"] + PORT_MARGIN
        z0, z1 = board_z + q["z_min"] - PORT_MARGIN, board_z + q["z_max"] + PORT_MARGIN
        d.openings.append(Opening(w.name, q["id"], q["label"], u0, u1, z0, z1,
                                  rect_pts(w, u0, u1, z0, z1),
                                  math.degrees(math.atan2(w.eu[1], w.eu[0]))))

    # Lid on the near wall, tuck flap on the lid
    near = walls["near"]
    lid0, lid1 = Hw, Hw + W + 2 * T
    d.panels.append(Panel("lid", rect_pts(near, -T, L + T, lid0, lid1), "LID"))
    d.hinges.append((near.pt(0, Hw), near.pt(L, Hw)))
    tuck_depth = min(TUCK_MAX, 0.6 * H_in)
    tuck_w = L - 2 * (TAB_W + 1)  # clear of the glue tabs at the far corners
    c = min(5.0, tuck_depth / 2)
    a, b = (L - tuck_w) / 2, (L + tuck_w) / 2
    tuck_local = [(a, lid1), (b, lid1), (b, lid1 + tuck_depth - c), (b - c, lid1 + tuck_depth),
                  (a + c, lid1 + tuck_depth), (a, lid1 + tuck_depth - c)]
    d.panels.append(Panel("tuck", [near.pt(u, z) for u, z in tuck_local], "TUCK"))
    d.hinges.append((near.pt(a, lid1), near.pt(b, lid1)))
    d.dims.update(tuck_depth=tuck_depth, tuck_w=tuck_w)
    if cl["far"] < T + 1:
        d.errors.append("far clearance is too small for the tuck flap")

    # Dust flaps on the end walls, short of the far wall so the tuck can pass
    for name in ("left", "right"):
        w = walls[name]
        a, b = T + 0.5, W - T - 0.5
        dc = 3.0
        local = [(a, Hw), (b, Hw), (b, Hw + DUST_DEPTH - dc), (b - dc, Hw + DUST_DEPTH),
                 (a + dc, Hw + DUST_DEPTH), (a, Hw + DUST_DEPTH - dc)]
        d.panels.append(Panel(f"dust-{name}", [w.pt(u, z) for u, z in local], f"DUST FLAP, {name.upper()} END",
                              math.degrees(math.atan2(w.eu[1], w.eu[0]))))
        d.hinges.append((w.pt(a, Hw), w.pt(b, Hw)))

    # Glue tabs. Each corner's tab goes on whichever wall leaves it covering
    # the least opening area, preferring the end wall on a tie. The tuck flap
    # is narrow enough to clear tabs glued inside the far wall.
    corners = [
        ("near-left", [("left", 0, "near", 0), ("near", 0, "left", 0)]),
        ("near-right", [("right", 0, "near", 1), ("near", 1, "right", 0)]),
        ("far-left", [("left", 1, "far", 0), ("far", 0, "left", 1)]),
        ("far-right", [("right", 1, "far", 1), ("far", 1, "right", 1)]),
    ]
    for corner, options in corners:
        best = min((make_tab(d, *o) for o in options), key=lambda t: t[3])
        panel, hinge, holes, _, attach = best
        d.panels.append(panel)
        d.hinges.append(hinge)
        d.tab_holes.extend(holes)
        d.tab_attach[corner] = attach

    if doubler:
        d.notes.append("Doubler: a separate floor-sized piece glued on top of the floor.")
    check(d)
    return d


def make_tab(d, a_name, a_end, b_name, b_end):
    """Glue tab hinged on wall A's end, glued to the inside of wall B."""
    T, Hw = d.card, d.dims["Hw"]
    A, B = d.walls[a_name], d.walls[b_name]
    s = 1 if a_end else -1
    ua = A.length if a_end else 0
    g0, g1 = T + 0.5, 0.5
    local = [(0, g0), (TAB_W, g0 + TAB_TAPER), (TAB_W, Hw - g1 - TAB_TAPER), (0, Hw - g1)]
    pts = [A.pt(ua + s * dd, z) for dd, z in local]
    holes, area = [], 0.0
    for o in d.openings:
        if o.wall != b_name:
            continue
        d0, d1 = (o.u0, o.u1) if b_end == 0 else (B.length - o.u1, B.length - o.u0)
        d0, d1 = max(d0, 0), min(d1, TAB_W)
        z0, z1 = max(o.z0, g0), min(o.z1, Hw - g1)
        if d0 < d1 and z0 < z1:
            area += (d1 - d0) * (z1 - z0)
            holes.append([A.pt(ua + s * d0, z0), A.pt(ua + s * d1, z0),
                          A.pt(ua + s * d1, z1), A.pt(ua + s * d0, z1)])
    angle = math.degrees(math.atan2(A.ez[1], A.ez[0]))
    panel = Panel(f"tab-{a_name}-{b_name}", pts, "GLUE", angle, glue=True)
    return panel, (A.pt(ua, g0), A.pt(ua, Hw - g1)), holes, area, f"on {a_name} wall, glued to {b_name}"


# --- checks -----------------------------------------------------------------

def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _proper_cross(p1, p2, q1, q2, eps=1e-6):
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and \
           ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps))


def _inside(pt, poly):
    x, y = pt
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _centroid(poly):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return cx / (3 * a), cy / (3 * a)


def edges(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def check(d):
    p, T = d.params, d.card
    L, W, Hw = d.dims["L"], d.dims["W"], d.dims["Hw"]
    err = d.errors

    for x, y in d.holes:
        if min(x, y, L - x, W - y) < HOLE_EDGE_MIN:
            err.append(f"screw hole at ({x:.1f}, {y:.1f}) is within {HOLE_EDGE_MIN} mm of a floor fold")

    top_hinge = {"near": [(0, L)], "far": [],
                 "left": [(T + 0.5, W - T - 0.5)], "right": [(T + 0.5, W - T - 0.5)]}
    for o in d.openings:
        w = d.walls[o.wall]
        if o.z0 < FOLD_MIN:
            err.append(f"{o.port}: opening is {o.z0:.2f} mm from the floor fold")
        if o.u0 < FOLD_MIN or o.u1 > w.length - FOLD_MIN:
            err.append(f"{o.port}: opening is within {FOLD_MIN} mm of the {o.wall} wall's end")
        if any(a < o.u1 and o.u0 < b for a, b in top_hinge[o.wall]) and o.z1 > Hw - FOLD_MIN:
            err.append(f"{o.port}: opening is within {FOLD_MIN} mm of the {o.wall} wall's top fold")
        if o.wall == "far" and o.z1 > Hw - d.dims["tuck_depth"]:
            err.append(f"{o.port}: the tuck flap covers this far-wall opening")
    for i, a in enumerate(d.openings):
        for b in d.openings[i + 1:]:
            if a.wall == b.wall and a.u0 < b.u1 and b.u0 < a.u1 and a.z0 < b.z1 and b.z0 < a.z1:
                err.append(f"openings {a.port} and {b.port} overlap")

    lid = next(x for x in d.panels if x.name == "lid")
    xs, ys = [q[0] for q in lid.pts], [q[1] for q in lid.pts]
    if abs((max(xs) - min(xs)) - (L + 2 * T)) > 1e-6 or abs((max(ys) - min(ys)) - (W + 2 * T)) > 1e-6:
        err.append("lid is not the floor size plus 2 x card thickness")

    for i, a in enumerate(d.panels):
        for b in d.panels[i + 1:]:
            if any(_proper_cross(p1, p2, q1, q2) for p1, p2 in edges(a.pts) for q1, q2 in edges(b.pts)) \
                    or _inside(_centroid(a.pts), b.pts) or _inside(_centroid(b.pts), a.pts):
                err.append(f"panels {a.name} and {b.name} overlap")


# --- layout -------------------------------------------------------------------

def bbox(points):
    xs, ys = [q[0] for q in points], [q[1] for q in points]
    return min(xs), min(ys), max(xs), max(ys)


TITLE_W, TITLE_H = 80.0, 31.0


def layout(d):
    """Place the net, the title block and the doubler.

    The doubler goes under the net next to the title block if there is room,
    otherwise on a page of its own.
    """
    pw, ph = PAGES[d.paper]
    x0, y0, x1, y1 = bbox([q for pn in d.panels for q in pn.pts])
    nw, nh = x1 - x0, y1 - y0
    header = 8.0
    ox = (pw - nw) / 2 - x0
    oy = ph - MARGIN - header - y1
    below_top = ph - MARGIN - header - nh - 6
    L, W = d.dims["L"], d.dims["W"]

    def row_fits(with_doubler):
        row_w = (L + 8 if with_doubler else 0) + TITLE_W
        row_h = max(W if with_doubler else 0, TITLE_H)
        return below_top - row_h >= MARGIN and row_w <= pw - 2 * MARGIN

    beside = d.doubler and row_fits(True)
    own_page = d.doubler and not beside
    if nw > pw - 2 * MARGIN or not row_fits(False) or (own_page and L > pw - 2 * MARGIN):
        d.errors.append(f"net ({nw:.0f} x {nh:.0f} mm plus title) does not fit on {d.paper}")
    row_w = (L + 8 if beside else 0) + TITLE_W
    left = (pw - row_w) / 2
    if beside:
        doubler_at = (left, below_top - W)
    elif own_page:
        doubler_at = ((pw - L) / 2, ph - MARGIN - header - W)
    else:
        doubler_at = None
    title_at = (left + (L + 8 if beside else 0), below_top - TITLE_H)
    return dict(ox=ox, oy=oy, net_size=(nw, nh), doubler_at=doubler_at, doubler_page=own_page,
                title_at=title_at, page=(pw, ph))


# --- drawing ----------------------------------------------------------------

def _path(c, pts, ox, oy):
    path = c.beginPath()
    path.moveTo((pts[0][0] + ox) * MM, (pts[0][1] + oy) * MM)
    for x, y in pts[1:]:
        path.lineTo((x + ox) * MM, (y + oy) * MM)
    path.close()
    return path


def cut_and_fold_segments(d):
    """Split panel outlines into cut segments and fold (hinge) segments."""
    segs = [s for pn in d.panels for s in edges(pn.pts)]

    def key(s):
        (ax, ay), (bx, by) = s
        if abs(ay - by) < 1e-6:
            return ("h", round(ay, 5)), min(ax, bx), max(ax, bx)
        if abs(ax - bx) < 1e-6:
            return ("v", round(ax, 5)), min(ay, by), max(ay, by)
        return None, 0, 0

    def make(line, a, b):
        kind, c = line
        return ((a, c), (b, c)) if kind == "h" else ((c, a), (c, b))

    cuts = []
    for s in segs:
        line, a, b = key(s)
        if line is None:
            cuts.append(s)
            continue
        pieces = [(a, b)]
        for h in d.hinges:
            hl, ha, hb = key(h)
            if hl != line:
                continue
            nxt = []
            for pa, pb in pieces:
                if hb <= pa + 1e-6 or ha >= pb - 1e-6:
                    nxt.append((pa, pb))
                    continue
                if ha > pa + 1e-6:
                    nxt.append((pa, ha))
                if hb < pb - 1e-6:
                    nxt.append((hb, pb))
            pieces = nxt
        cuts.extend(make(line, pa, pb) for pa, pb in pieces if pb - pa > 1e-3)
    return cuts, list(d.hinges)


def _label(c, text, x, y, angle, size=6):
    c.saveState()
    c.translate(x * MM, y * MM)
    if angle in (90.0, -90.0):
        angle = 90.0
    elif abs(angle) == 180.0:
        angle = 0.0
    c.rotate(angle)
    c.setFont("Helvetica", size)
    c.drawCentredString(0, -size * 0.35, text)
    c.restoreState()


def draw_page1(c, d, lay):
    from reportlab.lib.colors import Color
    from reportlab.pdfbase.pdfmetrics import stringWidth
    p = d.params
    ox, oy = lay["ox"], lay["oy"]
    pw, ph = lay["page"]

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN * MM, (ph - MARGIN - 4) * MM, f"{p['model']}: fold-up card case")
    c.setFont("Helvetica", 7)
    c.drawRightString((pw - MARGIN) * MM, (ph - MARGIN - 4) * MM,
                      "Solid: cut.  Dashed: valley fold towards you.  Grey: cut out.  Print this side = inside.")

    # Board footprint on the floor, for orientation
    c.setStrokeColor(Color(0.6, 0.6, 0.6))
    c.setLineWidth(0.3)
    c.setDash([1, 2])
    c.drawPath(_path(c, d.board_outline, ox, oy), stroke=1, fill=0)
    c.setDash([])

    # Glue hatching
    for pn in d.panels:
        if not pn.glue:
            continue
        c.saveState()
        c.clipPath(_path(c, pn.pts, ox, oy), stroke=0, fill=0)
        x0, y0, x1, y1 = bbox(pn.pts)
        c.setStrokeColor(Color(0.55, 0.55, 0.55))
        c.setLineWidth(0.3)
        k = x0 - (y1 - y0)
        while k < x1:
            c.line((k + ox) * MM, (y0 + oy) * MM, (k + (y1 - y0) + ox) * MM, (y1 + oy) * MM)
            k += 1.5
        c.restoreState()

    # Openings (port cut-outs and matching holes in glue tabs)
    c.setFillColor(Color(0.82, 0.82, 0.82))
    c.setStrokeColor(Color(0, 0, 0))
    c.setLineWidth(0.4)
    for pts in [o.pts for o in d.openings] + d.tab_holes:
        c.drawPath(_path(c, pts, ox, oy), stroke=1, fill=1)
    c.setFillColor(Color(0, 0, 0))

    # Cut and fold lines
    cuts, folds = cut_and_fold_segments(d)
    c.setLineWidth(0.4)
    for (ax, ay), (bx, by) in cuts:
        c.line((ax + ox) * MM, (ay + oy) * MM, (bx + ox) * MM, (by + oy) * MM)
    c.setStrokeColor(Color(0.1, 0.25, 0.7))
    c.setDash([3, 2])
    for (ax, ay), (bx, by) in folds:
        c.line((ax + ox) * MM, (ay + oy) * MM, (bx + ox) * MM, (by + oy) * MM)
    c.setDash([])
    c.setStrokeColor(Color(0, 0, 0))

    # Screw holes
    for x, y in d.holes:
        _hole(c, x + ox, y + oy)

    # Labels
    for pn in d.panels:
        if pn.name.startswith("tab"):
            cx, cy = _centroid(pn.pts)
            _label(c, pn.label, cx + ox, cy + oy, pn.angle, 5)
            continue
        cx, cy = _centroid(pn.pts)
        if pn.name in ("near", "far", "left", "right"):
            w = d.walls[pn.name]
            gap, free = _free_spot(d, pn.name)
            if gap < stringWidth(pn.label, "Helvetica", 6) / MM + 4:
                continue  # no room between the openings; the dust flap names the end
            z = d.dims["Hw"] - (NOTCH_R + 4 if pn.name == "far" else 3.5)
            cx, cy = w.pt(free, z)
        _label(c, pn.label, cx + ox, cy + oy, pn.angle, 6 if pn.name != "floor" else 7)
    for o in d.openings:
        cx = sum(q[0] for q in o.pts) / 4
        cy = sum(q[1] for q in o.pts) / 4
        _label(c, o.label, cx + ox, cy + oy, o.angle, 4.5)

    if d.doubler and not lay["doubler_page"]:
        draw_doubler(c, d, *lay["doubler_at"])
    draw_title(c, d, *lay["title_at"])


def draw_doubler(c, d, dx, dy):
    L, W = d.dims["L"], d.dims["W"]
    c.setLineWidth(0.4)
    c.rect(dx * MM, dy * MM, L * MM, W * MM, stroke=1, fill=0)
    for x, y in d.holes:
        _hole(c, x + dx, y + dy)
    c.setFont("Helvetica", 7)
    c.drawCentredString((dx + L / 2) * MM, (dy + W / 2 + 2) * MM, "DOUBLER")
    c.setFont("Helvetica", 5.5)
    c.drawCentredString((dx + L / 2) * MM, (dy + W / 2 - 2.5) * MM,
                        "Cut out separately. Glue on top of the floor, printed side up,")
    c.drawCentredString((dx + L / 2) * MM, (dy + W / 2 - 5.5) * MM,
                        "with the holes lined up.")


def _hole(c, x, y):
    """Screw hole: circle with a crosshair at (x, y) in page mm."""
    r = HOLE_D / 2
    c.setLineWidth(0.4)
    c.circle(x * MM, y * MM, r * MM, stroke=1, fill=0)
    c.setLineWidth(0.25)
    c.line((x - r - 1.5) * MM, y * MM, (x + r + 1.5) * MM, y * MM)
    c.line(x * MM, (y - r - 1.5) * MM, x * MM, (y + r + 1.5) * MM)


def _free_spot(d, wall):
    """Widest gap between openings on a wall: (length, centre u)."""
    w = d.walls[wall]
    spans = sorted((o.u0, o.u1) for o in d.openings if o.wall == wall)
    best, gap_start = (0, w.length / 2), 0.0
    for a, b in spans + [(w.length, w.length)]:
        if a - gap_start > best[0]:
            best = (a - gap_start, (a + gap_start) / 2)
        gap_start = max(gap_start, b)
    return best


def draw_title(c, d, x, y):
    p, T = d.params, d.card
    top = y + TITLE_H
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x * MM, (top - 3) * MM, p["model"])
    c.setFont("Helvetica", 6.5)
    lines = [
        f"Card thickness {T} mm, spacers {SPACER:g} mm",
        f"Inside {d.dims['L']:.1f} x {d.dims['W']:.1f} x {d.dims['H_in']:.1f} mm (L x W x H)",
        f"make_case.py {VERSION}, {datetime.date.today().isoformat()}",
        "Print at 100% / Actual size.",
        "Check this bar measures 50 mm:",
    ]
    for i, s in enumerate(lines):
        c.drawString(x * MM, (top - 7.5 - i * 3.3) * MM, s)
    # 50 mm scale bar with 10 mm ticks
    by = top - 7.5 - len(lines) * 3.3 - 2
    c.setLineWidth(0.6)
    c.line(x * MM, by * MM, (x + SCALE_BAR) * MM, by * MM)
    for i in range(6):
        c.line((x + i * 10) * MM, by * MM, (x + i * 10) * MM, (by + (2 if i % 5 else 3)) * MM)
    c.setFont("Helvetica", 5)
    c.drawString(x * MM, (by - 3) * MM, "0")
    c.drawRightString((x + SCALE_BAR) * MM, (by - 3) * MM, "50 mm")
    # 20 mm square
    sq = 20.0
    c.setLineWidth(0.4)
    sx, sy = x + TITLE_W - sq, y + TITLE_H - sq - 4
    c.rect(sx * MM, sy * MM, sq * MM, sq * MM, stroke=1, fill=0)
    c.setFont("Helvetica", 5)
    c.drawCentredString((sx + sq / 2) * MM, (sy + sq / 2 - 1) * MM, "20 mm square")


def draw_page2(c, d):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Frame, Paragraph, Table, TableStyle

    p, T = d.params, d.card
    pw, ph = PAGES[d.paper]
    ss = getSampleStyleSheet()
    body = ss["BodyText"].clone("b", fontSize=8, leading=10, spaceBefore=0, spaceAfter=2)
    small = ss["BodyText"].clone("s", fontSize=7, leading=8.5, spaceBefore=0, spaceAfter=0)
    h = ss["Heading2"].clone("h", fontSize=11, spaceBefore=6, spaceAfter=3)

    def flag(ok):
        return "" if ok else '<font color="#b00000"><b>UNVERIFIED</b></font> '

    story = [Paragraph(f"{p['model']}: assembly", ss["Heading1"].clone("h1", fontSize=14))]

    rows = [["Item", "Value", "Source"]]
    b = p["board"]
    for name, key in (("Board length", "length"), ("Board width", "width"), ("PCB thickness", "thickness")):
        rows.append([name, f"{val(b[key]):g} mm", Paragraph(flag(b[key]["verified"]) + b[key]["source"], small)])
    rows.append(["Screw holes", f"{len(p['holes']['positions'])} x {p['holes']['diameter']:g} mm",
                 Paragraph(flag(p["holes"]["verified"]) + p["holes"]["source"], small)])
    for name, key in (("Tallest part above PCB", "height_above"), ("Deepest part below PCB", "depth_below")):
        rows.append([name, f"{val(p[key]):g} mm", Paragraph(flag(p[key]["verified"]) + p[key]["source"], small)])
    for q in p["ports"]:
        rows.append([f"{q['label']} ({q['edge']} edge)",
                     f"{q['from']:g}–{q['to']:g}, z {q['z_min']:g} to {q['z_max']:g}",
                     Paragraph(flag(q["verified"]) + q["source"], small)])
    rows.append(["Card thickness", f"{T:g} mm", "setting"])
    rows.append(["Spacers", f"{SPACER:g} mm", "fixed"])
    cl = d.clearance
    rows.append(["Board-to-wall gap", f"near {cl['near']:.2f}, far {cl['far']:.2f}, left {cl['left']:.2f}, "
                 f"right {cl['right']:.2f}", "connector overhang + 1 mm, at least 2 mm"])
    rows.append(["Inside size", f"{d.dims['L']:.1f} x {d.dims['W']:.1f} x {d.dims['H_in']:.1f} mm",
                 "board + gaps; height = spacer + PCB + tallest part + 3 mm"])
    t = Table(rows, colWidths=[38 * MM, 50 * MM, 92 * MM], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    story += [Paragraph("Dimensions", h), t]

    through = [q["label"] for q in p["ports"] if q.get("protrudes_through")]
    steps = [
        f"Print page 1 at 100% (Actual size) on card about {T} mm thick (around 250–300 gsm). "
        "Check that the scale bar measures 50 mm.",
        "Cut along the solid lines, including the grey openings, the holes in the glue tabs and the thumb notch. "
        "Cut out the doubler separately.",
        f"Make the four screw holes in the floor and the doubler ({HOLE_D} mm, a hole punch or a sharp pencil works).",
        "Score every dashed line with a blunt point against a ruler. Every fold is a valley fold "
        "towards the printed side, which becomes the inside of the case.",
        "Glue the doubler on top of the floor, printed side up. Push a screw through to line up the holes.",
        "Fold up the four walls. Fold each glue tab in and glue it to the inside of the wall next to it. "
        "Hold each corner square until the glue grabs.",
        "Push the standoffs' threads down through the floor holes from the inside and fit the nuts underneath.",
        ("Take out the " + " and ".join(through) + " card. " if through else "")
        + "Lower the Pi onto the standoffs with each connector facing its opening, and screw it down.",
    ]
    if through:
        steps.append("Push the " + " and ".join(through) + " card back in through its slot in the wall.")
    steps.append("Fold the dust flaps in, fold the lid over and push the tuck flap down inside the far wall. "
                 "Use the thumb notch to open it.")
    story += [Paragraph("Steps", h)] + [Paragraph(f"{i}. {s}", body) for i, s in enumerate(steps, 1)]

    parts = [f"4 x M2.5 nylon standoffs, male–female, {SPACER:g} mm body, thread at least 4 mm",
             "4 x M2.5 nylon nuts (under the floor)",
             "4 x M2.5 x 5 mm nylon screws (through the Pi into the standoffs)",
             "Glue stick or PVA"]
    story += [Paragraph("Parts", h)] + [Paragraph("• " + s, body) for s in parts]

    notes = list(p.get("notes", [])) + [
        "The case has no vents. Under sustained load the Pi will run warm and may throttle.",
        "Tabs: " + "; ".join(f"{k} {v}" for k, v in d.tab_attach.items()) + ".",
    ]
    story += [Paragraph("Notes", h)] + [Paragraph("• " + s, body) for s in notes]
    story += [Paragraph("Section through the middle, seen from the right", h),
              section_drawing(d)]

    while story:
        frame = Frame(MARGIN * MM, MARGIN * MM, (pw - 2 * MARGIN) * MM, (ph - 2 * MARGIN) * MM,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        frame.addFromList(story, c)
        if story:
            c.showPage()


def section_drawing(d):
    """Side section: near wall on the left, far wall and tuck on the right."""
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    p, T = d.params, d.card
    W, H_in, Hw = d.dims["W"], d.dims["H_in"], d.dims["Hw"]
    s = 1.1  # drawing scale
    pad = 7
    dr = Drawing((W + 2 * pad + 40) * s * MM, (Hw + 2 * pad) * s * MM)

    def X(v):
        return (pad + v) * s * MM

    def Y(v):
        return (pad + v) * s * MM

    def box(x0, y0, x1, y1, fill=None, stroke=colors.black, w=0.6, dash=None):
        r = Rect(X(x0), Y(y0), X(x1) - X(x0), Y(y1) - Y(y0), fillColor=fill, strokeColor=stroke, strokeWidth=w)
        if dash:
            r.strokeDashArray = dash
        dr.add(r)

    card = colors.Color(0.75, 0.6, 0.4)
    box(-T, -T, W + T, 0, card, w=0.3)                              # floor
    box(-T, 0, 0, Hw - T, card, w=0.3)                              # near wall
    box(W, 0, W + T, Hw - T, card, w=0.3)                           # far wall
    box(-T, Hw - T, W + T, Hw, card, w=0.3)                         # lid
    box(W - T, Hw - T - d.dims["tuck_depth"], W, Hw - T, card, w=0.3)  # tuck
    cl = d.clearance
    pcb = val(p["board"]["thickness"])
    bz = SPACER
    box(cl["near"], bz, cl["near"] + val(p["board"]["width"]), bz + pcb, colors.Color(0.2, 0.55, 0.3), w=0.3)
    for hy in sorted({h[1] for h in p["holes"]["positions"]}):
        box(cl["near"] + hy - 1.5, 0, cl["near"] + hy + 1.5, bz, colors.Color(0.85, 0.85, 0.85), w=0.3)
    tallest = val(p["height_above"])
    box(cl["near"], bz + pcb, cl["near"] + val(p["board"]["width"]), bz + pcb + tallest,
        None, colors.grey, 0.4, [2, 2])
    dr.add(String(X(W + T + 3), Y(Hw - 3), "lid", fontName="Helvetica", fontSize=6))
    dr.add(String(X(W + T + 3), Y(Hw - d.dims["tuck_depth"] / 2 - 2), "tuck inside far wall", fontName="Helvetica", fontSize=6))
    dr.add(String(X(W + T + 3), Y(bz + pcb / 2 - 1), f"PCB on {SPACER:g} mm spacers", fontName="Helvetica", fontSize=6))
    dr.add(String(X(cl["near"] + 2), Y(bz + pcb + tallest - 4), f"space for the tallest part ({tallest:g} mm)", fontName="Helvetica", fontSize=6))
    dr.add(String(X(-T), Y(-T) - 9, "near wall (lid hinge)", fontName="Helvetica", fontSize=6))
    return dr


def render(d, out):
    from reportlab.pdfgen import canvas
    lay = layout(d)
    pw, ph = lay["page"]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(pw * MM, ph * MM))
    c.setTitle(f"{d.params['model']} card case")
    c.setCreator(f"make_case.py {VERSION}")
    draw_page1(c, d, lay)
    c.showPage()
    if lay["doubler_page"]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN * MM, (ph - MARGIN - 4) * MM, f"{d.params['model']}: floor doubler (print at 100%)")
        draw_doubler(c, d, *lay["doubler_at"])
        c.showPage()
    draw_page2(c, d)
    c.showPage()
    c.save()
    return lay


def previews(pdf, dpi=150):
    import fitz
    doc = fitz.open(str(pdf))
    paths = []
    for i, page in enumerate(doc):
        png = Path(pdf).with_name(f"{Path(pdf).stem}-p{i + 1}.png")
        page.get_pixmap(dpi=dpi).save(str(png))
        paths.append(png)
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("params", help="board parameters JSON (params/<model>.json)")
    ap.add_argument("-o", "--out", help="output PDF (default out/<id>-case.pdf)")
    ap.add_argument("--card", type=float, default=0.4, help="card thickness in mm (default 0.4)")
    ap.add_argument("--paper", choices=sorted(PAGES), default="A4")
    ap.add_argument("--no-doubler", action="store_true", help="leave out the floor doubler")
    ap.add_argument("--preview", action="store_true", help="also write 150 dpi PNGs of each page")
    a = ap.parse_args(argv)

    p = load_params(a.params)
    d = design(p, card=a.card, paper=a.paper, doubler=not a.no_doubler)
    out = Path(a.out or f"out/{p['id']}-case.pdf")
    layout(d)  # adds a fit error before rendering
    if d.errors:
        for e in d.errors:
            print("error:", e, file=sys.stderr)
        return 1
    render(d, out)
    print(f"{out}: inside {d.dims['L']:.1f} x {d.dims['W']:.1f} x {d.dims['H_in']:.1f} mm, "
          f"gaps near {d.clearance['near']:.2f} far {d.clearance['far']:.2f} "
          f"left {d.clearance['left']:.2f} right {d.clearance['right']:.2f}")
    if a.preview:
        for png in previews(out):
            print(png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
