import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeforge.geometry import (
    LRA,
    GeometryError,
    LRARow,
    bends,
    centerline,
    developed_length,
    lra_to_xyz,
    rigid_distance,
    straight_lengths,
    xyz_to_lra,
)
from pipeforge.parts import sample_parts

SAMPLES = sample_parts()

# Two 90 degree bends at CLR 20, worked by hand in docs/ENGINEERING_NOTES.md section 1.5:
# tangent length T = 20 tan 45 = 20, so the straights are 100-20, 100-20-20 and 100-20.
HAND = np.array([[0, 0, 0], [100, 0, 0], [100, 100, 0], [100, 100, 100]], float)


def test_five_samples_exist():
    assert len(SAMPLES) == 5


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_xyz_lra_xyz_round_trip_within_0_01_mm(part_no):
    part = SAMPLES[part_no]
    back = lra_to_xyz(part.lra())
    assert np.max(np.abs(back - part.points)) < 0.01
    assert np.max(np.abs(back - part.points)) < 1e-9  # in practice it is exact


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_round_trip_without_placement_is_the_same_shape(part_no):
    part = SAMPLES[part_no]
    lra = part.lra()
    bare = LRA(rows=lra.rows, final_L=lra.final_L)  # what a bender program carries
    assert rigid_distance(lra_to_xyz(bare), part.points) < 0.01


def test_hand_computed_two_bend_case():
    lra = xyz_to_lra(HAND, 20.0)
    assert [round(r.L, 9) for r in lra.rows] == [80.0, 60.0]
    assert lra.final_L == pytest.approx(80.0)
    assert [r.A for r in lra.rows] == pytest.approx([90.0, 90.0])
    # plane normal turns from +Z to +X about the feed direction +Y: +90 deg
    assert [r.R for r in lra.rows] == pytest.approx([0.0, 90.0])
    assert developed_length(lra) == pytest.approx(220.0 + 20.0 * math.pi)


def test_single_bend_tangent_points_and_centre():
    (b,) = bends(np.array([[0, 0, 0], [100, 0, 0], [100, 100, 0]], float), 20.0)
    assert b.t_in == pytest.approx([80, 0, 0])
    assert b.t_out == pytest.approx([100, 20, 0])
    assert b.centre == pytest.approx([80, 20, 0])
    assert b.arc_len == pytest.approx(10 * math.pi)


def test_overlapping_bends_are_rejected_with_the_segment_named():
    with pytest.raises(GeometryError, match="segment 1"):
        xyz_to_lra(np.array([[0, 0, 0], [10, 0, 0], [10, 50, 0]], float), 20.0)


def test_collinear_point_is_rejected():
    with pytest.raises(GeometryError, match="collinear"):
        xyz_to_lra(np.array([[0, 0, 0], [50, 0, 0], [100, 0, 0]], float), 10.0)


def test_fold_back_is_rejected():
    with pytest.raises(GeometryError, match="fold back"):
        xyz_to_lra(np.array([[0, 0, 0], [100, 0, 0], [0, 0.001, 0]], float), 10.0)


def test_repeated_point_is_rejected():
    with pytest.raises(GeometryError, match="coincide"):
        xyz_to_lra(np.array([[0, 0, 0], [0, 0, 0], [1, 1, 0]], float), 10.0)


def test_per_bend_radius_count_must_match():
    with pytest.raises(GeometryError, match="radii"):
        xyz_to_lra(HAND, [20.0])


def test_straight_tube_has_no_bends():
    lra = xyz_to_lra(np.array([[0, 0, 0], [0, 0, 250]], float), 10.0)
    assert lra.n_bends == 0 and lra.final_L == pytest.approx(250)
    assert lra_to_xyz(lra) == pytest.approx(np.array([[0, 0, 0], [0, 0, 250]]))


def test_centerline_arcs_lie_on_the_bend_radius():
    part = SAMPLES["PF-HB-2201"]
    for b in bends(part.points, part.clr):
        arc = centerline(np.array([b.point - b.u * 200, b.point, b.point + b.v * 200]), b.clr, step_deg=1)
        on_arc = arc[2:-1]
        assert np.linalg.norm(on_arc - b.centre, axis=1) == pytest.approx(b.clr, abs=1e-9)


@pytest.mark.parametrize("part_no", sorted(SAMPLES))
def test_sampled_centerline_length_converges_to_developed_length(part_no):
    part = SAMPLES[part_no]
    poly = centerline(part.points, part.clr, step_deg=0.25)
    length = float(np.sum(np.linalg.norm(np.diff(poly, axis=0), axis=1)))
    assert length == pytest.approx(part.cut_length(), rel=1e-5)
    assert length <= part.cut_length() + 1e-9  # chords are never longer than arcs


def test_elongation_allowance_shortens_only_the_arcs():
    lra = xyz_to_lra(HAND, 20.0)
    arcs = 20.0 * math.pi
    assert developed_length(lra, elongation_pct=10) == pytest.approx(220.0 + 0.9 * arcs)


def test_straights_sum_with_tangents_to_segment_lengths():
    part = SAMPLES["PF-FL-0807"]
    bl = bends(part.points, part.clr)
    s = straight_lengths(part.points, bl)
    t = [0.0] + [b.tangent_len for b in bl] + [0.0]
    seg = np.linalg.norm(np.diff(part.points, axis=0), axis=1)
    assert np.array(s) + np.array(t[:-1]) + np.array(t[1:]) == pytest.approx(seg)


rows = st.lists(
    st.tuples(
        st.floats(0.0, 300.0),  # L
        st.floats(-179.0, 179.0),  # R
        st.floats(5.0, 170.0),  # A
        st.floats(5.0, 120.0),  # CLR
    ),
    min_size=1,
    max_size=6,
)


@settings(max_examples=150, deadline=None)
@given(rows=rows, final=st.floats(0.0, 300.0))
def test_lra_xyz_lra_property(rows, final):
    program = LRA(rows=tuple(LRARow(L, R, A, c) for L, R, A, c in rows), final_L=final)
    program = LRA(rows=(LRARow(program.rows[0].L, 0.0, program.rows[0].A, program.rows[0].clr), *program.rows[1:]),
                  final_L=final)
    pts = lra_to_xyz(program)
    back = xyz_to_lra(pts, [r.clr for r in program.rows])
    for a, b in zip(program.rows, back.rows, strict=True):
        assert pytest.approx(a.L, abs=1e-6) == b.L
        assert pytest.approx(a.A, abs=1e-6) == b.A
        dr = (b.R - a.R + 180.0) % 360.0 - 180.0
        assert abs(dr) < 1e-6
    assert back.final_L == pytest.approx(final, abs=1e-6)
