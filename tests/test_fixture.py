import numpy as np
import pytest

from pipeforge import cad
from pipeforge.fixture import MIN_HEIGHT, design_fixture, fixture_frame
from pipeforge.parts import sample_parts

SAMPLES = sample_parts()


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_every_sample_gets_a_3_2_1_datum_scheme(part_no):
    fx = design_fixture(SAMPLES[part_no])
    datums = ",".join(b.datum for b in fx.blocks if b.datum).split(",")
    assert {"A1", "A2", "A3", "B1", "B2"} <= set(datums)
    assert [e.id for e in fx.end_stops] == ["C1", "E2"]
    assert len(fx.blocks) >= 6


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_frame_is_a_proper_rotation_and_the_part_clears_the_plate(part_no):
    part = SAMPLES[part_no]
    rot, _ = fixture_frame(part.points, part.clr)
    assert rot @ rot.T == pytest.approx(np.eye(3), abs=1e-9)
    assert np.linalg.det(rot) == pytest.approx(1.0)
    fx = design_fixture(part)
    from pipeforge.geometry import centerline

    lowest = centerline(fx.points, fx.clr, step_deg=1.0)[:, 2].min() - part.od / 2
    assert lowest == pytest.approx(MIN_HEIGHT, abs=0.05)


def test_blocks_sit_under_the_tube_centerline():
    fx = design_fixture(SAMPLES["PF-FT-2541"])
    from pipeforge.fixture import dense_centerline

    dense = dense_centerline(fx.points, fx.clr, spacing=0.5)
    for b in fx.blocks:
        assert np.min(np.linalg.norm(dense - b.contact, axis=1)) < 0.6
        assert b.height == pytest.approx(b.contact[2])


def test_a_steep_straight_gets_no_block_and_is_reported():
    fx = design_fixture(SAMPLES["PF-FL-0807"])
    assert any("too steep" in r for r in fx.rejected)


def test_station_sensors_one_per_clamp_plus_two_ends():
    fx = design_fixture(SAMPLES["PF-HB-2201"])
    clamps = sum(b.clamp for b in fx.blocks)
    assert clamps == 3
    assert len(fx.sensors()) == clamps + 2


def test_without_station_there_are_no_sensors():
    fx = design_fixture(SAMPLES["PF-HB-2201"], with_station=False)
    assert fx.sensors() == []


def test_mounting_holes_lie_inside_the_plate():
    fx = design_fixture(SAMPLES["PF-CP-1610"])
    for x, y in fx.holes:
        assert fx.plate_min[0] < x < fx.plate_max[0] and fx.plate_min[1] < y < fx.plate_max[1]


@pytest.mark.cad
@pytest.mark.skipif(not cad.available(), reason="CadQuery not installed")
def test_go_no_go_nominal_tube_seats_shifted_tube_does_not():
    """The groove clearance is the gauge: 0.3 mm clears, a 0.6 mm lateral error does not."""
    from pipeforge.fixture import fixture_solids

    part = SAMPLES["PF-HB-2201"]
    fx = design_fixture(part, clearance=0.3)
    solids = fixture_solids(fx)
    nominal = cad.rod_solid(fx.points, fx.clr, part.od)
    for name, blk in solids["blocks"]:
        assert blk.intersect(nominal).val().Volume() < 1e-3, name
    # shift sideways (in the plate plane, across the first straight) by twice the clearance
    d = fx.points[1] - fx.points[0]
    side = np.cross([0, 0, 1.0], d / np.linalg.norm(d))
    shifted = cad.rod_solid(fx.points + side * 0.6, fx.clr, part.od)
    hit = sum(blk.intersect(shifted).val().Volume() > 1e-3 for _, blk in solids["blocks"])
    assert hit >= 2


@pytest.mark.cad
@pytest.mark.skipif(not cad.available(), reason="CadQuery not installed")
def test_every_block_has_a_groove_cut():
    from pipeforge.fixture import fixture_solids

    fx = design_fixture(SAMPLES["PF-FT-2541"])
    solids = fixture_solids(fx)
    for b, (_, blk) in zip(fx.blocks, solids["blocks"], strict=True):
        box = b.length * b.width * b.height
        assert blk.val().Volume() < box - 1.0
