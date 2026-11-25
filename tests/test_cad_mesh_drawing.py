import math
from collections import Counter

import numpy as np
import pytest

from pipeforge import cad
from pipeforge.drawing import DrawingInfo, choose_scale, make_drawing
from pipeforge.mesh import tube_mesh
from pipeforge.parts import sample_parts

SAMPLES = sample_parts()


def test_mesh_is_closed_and_manifold():
    part = SAMPLES["PF-BL-0476"]
    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=16)
    edges = Counter()
    for a, b, c in m.faces:
        for e in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted(e))] += 1
    assert set(edges.values()) == {2}


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_mesh_volume_matches_polygon_corrected_exact_volume(part_no):
    part = SAMPLES[part_no]
    seg = 48
    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=seg, step_deg=2.0)
    exact = cad.expected_volume(part.od, part.wall, part.cut_length())
    polygon = (seg / (2 * math.pi)) * math.sin(2 * math.pi / seg)  # inscribed 48-gon area ratio
    assert m.volume() == pytest.approx(exact * polygon, rel=1e-3)


def test_mesh_stl_is_binary_with_the_right_triangle_count(tmp_path):
    part = SAMPLES["PF-CP-1610"]
    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=12)
    path = m.write_stl(tmp_path / "p.stl")
    data = path.read_bytes()
    n = int.from_bytes(data[80:84], "little")
    assert n == len(m.faces) and len(data) == 84 + 50 * n


@pytest.mark.cad
@pytest.mark.skipif(not cad.available(), reason="CadQuery not installed")
@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_cad_solid_is_valid_and_its_volume_is_exact(part_no):
    part = SAMPLES[part_no]
    solid = cad.tube_solid(part.points, part.clr, part.od, part.wall)
    assert solid.val().isValid()
    exact = cad.expected_volume(part.od, part.wall, part.cut_length())
    assert cad.solid_volume(solid) == pytest.approx(exact, rel=1e-6)


@pytest.mark.cad
@pytest.mark.skipif(not cad.available(), reason="CadQuery not installed")
def test_step_export_reimports_with_the_same_volume(tmp_path):
    import cadquery as cq

    part = SAMPLES["PF-HB-2201"]
    solid = cad.tube_solid(part.points, part.clr, part.od, part.wall)
    cad.export(solid, tmp_path / "hb.step", tmp_path / "hb.stl")
    back = cq.importers.importStep(str(tmp_path / "hb.step"))
    assert back.val().Volume() == pytest.approx(cad.solid_volume(solid), rel=1e-6)
    assert (tmp_path / "hb.stl").stat().st_size > 10_000


def test_scale_picks_the_largest_standard_scale_that_fits():
    small = {"FRONT": (100.0, 50.0), "TOP": (100.0, 40.0), "RIGHT": (40.0, 50.0)}
    big = {"FRONT": (800.0, 100.0), "TOP": (800.0, 140.0), "RIGHT": (140.0, 100.0)}
    assert choose_scale(small, 258, 229) == 1.0
    assert choose_scale(big, 258, 229) == 0.2


def test_drawing_writes_pdf_and_svg_with_bend_table(tmp_path):
    part = SAMPLES["PF-HB-2201"]
    info = DrawingInfo(part.part_no, part.name, part.material, part.od, part.wall)
    out = make_drawing(part.points, part.clr, info, tmp_path / "d.pdf", tmp_path / "d.svg")
    assert (tmp_path / "d.pdf").read_bytes()[:5] == b"%PDF-"
    svg = (tmp_path / "d.svg").read_text(encoding="utf-8")
    assert "BEND TABLE" in svg and "THIRD ANGLE" in svg and part.part_no in svg
    assert out["scale"] == "1:5"
    assert out["cut_length"] == pytest.approx(part.cut_length())
    assert len(out["rows"]) == len(part.points)
    assert np.isfinite(out["cut_length"])
