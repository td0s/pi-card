import json
from pathlib import Path

import fitz
import pytest

import make_case as mc

ROOT = Path(__file__).resolve().parent.parent
PARAMS = sorted((ROOT / "params").glob("*.json"))


@pytest.fixture(params=PARAMS, ids=lambda p: p.stem)
def params(request):
    return mc.load_params(request.param)


def test_registry_lists_every_params_file():
    listed = {m["params"] for m in json.loads((ROOT / "models.json").read_text())["models"]}
    assert listed == {f"params/{p.name}" for p in PARAMS}


@pytest.mark.parametrize("card", [0.3, 0.4, 0.5])
def test_design_passes_checks(params, card):
    d = mc.design(params, card=card)
    mc.layout(d)
    assert d.errors == []


def test_openings_match_connectors(params):
    d = mc.design(params)
    pcb = params["board"]["thickness"]["value"]
    m = mc.PORT_MARGIN
    for q in params["ports"]:
        o = next(o for o in d.openings if o.port == q["id"])
        offset = d.clearance["left"] if q["edge"] in ("near", "far") else d.clearance["near"]
        assert o.wall == q["edge"]
        assert o.u0 == pytest.approx(offset + q["from"] - m)
        assert o.u1 == pytest.approx(offset + q["to"] + m)
        # Heights include the floor card, the 5 mm spacer and the PCB
        assert o.z0 == pytest.approx(d.card + 5 + pcb + q["z_min"] - m)
        assert o.z1 == pytest.approx(d.card + 5 + pcb + q["z_max"] + m)


def test_spacer_height_sets_wall_height(params):
    d = mc.design(params, card=0.4)
    pcb = params["board"]["thickness"]["value"]
    assert d.dims["H_in"] == pytest.approx(5 + pcb + params["height_above"]["value"] + mc.HEADROOM)
    assert d.dims["Hw"] == pytest.approx(d.dims["H_in"] + 0.4)


def test_lid_is_landscape_and_tucks_into_far_wall(params):
    d = mc.design(params)
    assert d.dims["L"] > d.dims["W"]
    assert d.dims["lid_L"] == pytest.approx(d.dims["L"] + 2 * d.card)
    assert d.dims["lid_W"] == pytest.approx(d.dims["W"] + 2 * d.card)
    assert not [o for o in d.openings if o.wall == "far"]


def test_holes_follow_the_board(params):
    d = mc.design(params)
    for (hx, hy), (x, y) in zip(params["holes"]["positions"], d.holes):
        assert (x, y) == pytest.approx((d.clearance["left"] + hx, d.clearance["near"] + hy))


def test_overlapping_panels_are_reported(params):
    d = mc.design(params)
    d.panels.append(mc.Panel("bogus", [(1, 1), (5, 1), (5, 5), (1, 5)]))
    d.errors.clear()
    mc.check(d)
    assert any("bogus" in e for e in d.errors)


def test_pdf_is_full_scale(params, tmp_path):
    d = mc.design(params)
    pdf = tmp_path / "case.pdf"
    mc.render(d, pdf)
    doc = fitz.open(pdf)
    assert len(doc) == 2
    page = doc[0]
    assert page.rect.width == pytest.approx(210 * mc.MM, abs=0.01)
    lengths = []
    for g in page.get_drawings():
        for item in g["items"]:
            if item[0] == "l" and abs(item[1].y - item[2].y) < 1e-3:
                lengths.append(abs(item[2].x - item[1].x))
    assert any(abs(n - 50 * mc.MM) < 0.01 for n in lengths), "no 50 mm scale bar found"


def test_too_big_for_the_page_is_an_error(params):
    big = json.loads(json.dumps(params))
    big["board"]["length"]["value"] = 160
    d = mc.design(big)
    mc.layout(d)
    assert any("does not fit" in e for e in d.errors)


def test_doubler_moves_to_its_own_page_on_letter(params, tmp_path):
    d = mc.design(params, paper="Letter")
    lay = mc.layout(d)
    assert d.errors == []
    pdf = tmp_path / "case.pdf"
    mc.render(d, pdf)
    assert lay["doubler_page"] == ("floor doubler" in fitz.open(pdf)[1].get_text())
