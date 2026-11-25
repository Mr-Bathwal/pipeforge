import math

import numpy as np
import pytest

from pipeforge.compensation import as_lra_after_springback, compensate, no_springback
from pipeforge.dfm import (
    FAIL,
    PASS,
    WARN,
    Machine,
    check_part,
    clamp_length,
    collision_scan,
    min_between_bends,
    tooling_for,
)
from pipeforge.geometry import LRA, LRARow, lra_to_xyz, xyz_to_lra
from pipeforge.materials import MATERIALS
from pipeforge.mechanics import (
    _moment_factor,
    ovality_estimate,
    physics_model,
    springback,
    springback_band,
    wall_change,
)
from pipeforge.parts import Part, sample_parts

SAMPLES = sample_parts()


# ------------------------------------------------------------------ mechanics, worked examples (ENGINEERING_NOTES)


def test_wall_change_worked_example():
    # OD 22.2, t 1.6, CLR 60: t_o = 1.6 * 60 / 71.1, t_i = 1.6 * 60 / 48.9
    w = wall_change(22.2, 1.6, 60.0)
    assert w.t_outer == pytest.approx(1.6 * 60 / 71.1)
    assert w.t_inner == pytest.approx(1.6 * 60 / 48.9)
    assert w.thinning_pct == pytest.approx(100 * 11.1 / 71.1)
    assert w.thickening_pct == pytest.approx(100 * 11.1 / 48.9)


def test_thinning_formula_is_one_over_2r_over_d_plus_one():
    for d_ratio in (1.5, 2.0, 3.0, 5.0):
        w = wall_change(20.0, 1.0, 20.0 * d_ratio)
        assert w.thinning_pct == pytest.approx(100.0 / (2 * d_ratio + 1))


def test_wall_change_rejects_impossible_radius():
    with pytest.raises(ValueError):
        wall_change(20.0, 1.0, 9.0)


def test_moment_factor_limits():
    assert _moment_factor(0.0) == 1.0
    # a section that has only just yielded (alpha -> pi/2) carries the elastic moment, pi/4 of Mp
    assert _moment_factor(math.pi / 2 - 1e-6) == pytest.approx(math.pi / 4, rel=1e-4)


def test_springback_worked_example_matches_closed_form():
    # 22 x 1 mm tube, CLR 33, 47 deg, E 193 GPa, flow stress 205 MPa (fully plastic limit):
    # ratio = 4 sigma R / (pi E r_m) with r_m = 10.5
    sb = springback(47.0, 33.0, 22.0, 1.0, 193_000.0, 205.0)
    closed = 47.0 * 4 * 205.0 * 33.0 / (math.pi * 193_000.0 * 10.5)
    assert sb.springback_deg == pytest.approx(closed, rel=0.01)  # elastic core is under 1 %
    assert sb.plastic_fraction > 0.97
    assert sb.radius_after == pytest.approx(33.0 / (1 - sb.ratio))


def test_springback_grows_with_radius_and_strength():
    a = springback(90, 40, 20, 1.5, 200_000, 250).springback_deg
    assert springback(90, 80, 20, 1.5, 200_000, 250).springback_deg > a
    assert springback(90, 40, 20, 1.5, 200_000, 400).springback_deg > a
    assert springback(90, 40, 20, 1.5, 70_000, 250).springback_deg > a  # aluminium-like modulus


def test_springback_band_is_ordered():
    band = springback_band(90, 60, 22.2, 1.6, MATERIALS["STKM13A"])
    assert band.low.springback_deg < band.mid.springback_deg < band.high.springback_deg


def test_band_refuses_a_grade_without_yield_strength():
    with pytest.raises(ValueError, match="no specified minimum yield"):
        springback_band(90, 60, 25.4, 1.2, MATERIALS["STKM11A"])


# ------------------------------------------------------------------ compensation


def test_no_springback_gives_ybc_equal_to_lra():
    lra = SAMPLES["PF-HB-2201"].lra()
    prog = compensate(lra)
    for r, row in zip(prog.rows, lra.rows, strict=True):
        assert pytest.approx((row.L, row.R, row.A)) == (r.Y, r.B, r.C)
    assert prog.cut_length == pytest.approx(SAMPLES["PF-HB-2201"].cut_length())


def test_compensated_program_reproduces_the_nominal_points():
    part = SAMPLES["PF-FL-0807"]
    lra = part.lra()
    model = physics_model(part.od, part.wall, MATERIALS["SUS304"])
    prog = compensate(lra, model, "physics")
    made = as_lra_after_springback(prog, part.radii)
    bare = LRA(rows=lra.rows, final_L=lra.final_L)
    assert np.abs(lra_to_xyz(made) - lra_to_xyz(bare)).max() < 1e-6
    assert all(r.nominal_A < r.C for r in prog.rows)


def test_without_radius_growth_correction_the_part_comes_out_long():
    part = SAMPLES["PF-HB-2201"]
    lra = part.lra()
    model = lambda a, r: 0.05 * a  # noqa: E731  5 % springback, a large value to make the error visible
    wrong = compensate(lra, model, correct_radius_growth=False)
    made = lra_to_xyz(as_lra_after_springback(wrong, part.radii))
    nominal = lra_to_xyz(LRA(rows=lra.rows, final_L=lra.final_L))
    assert np.abs(made - nominal).max() > 1.0


def test_ybc_csv_has_one_line_per_bend(tmp_path):
    prog = compensate(SAMPLES["PF-BL-0476"].lra())
    text = prog.write_csv(tmp_path / "p.csv", "PF-BL-0476").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert lines[0] == "BEND,Y,B,C" and lines[-1].startswith("END")
    assert len(lines) == 2 + 4


def test_elongation_allowance_shortens_the_blank():
    lra = SAMPLES["PF-CP-1610"].lra()
    assert compensate(lra, elongation_pct=2).cut_length < compensate(lra).cut_length


def test_negative_springback_is_rejected():
    with pytest.raises(ValueError):
        compensate(SAMPLES["PF-HB-2201"].lra(), lambda a, r: -1.0)


def test_no_springback_model_is_zero():
    assert no_springback(90, 40) == 0.0


# ------------------------------------------------------------------ DFM


def _part(points, clr, od=20.0, wall=1.5, material="STKM13A", part_no="T"):
    return Part(part_no=part_no, name="t", material=material, od=od, wall=wall, clr=clr,
                points=np.asarray(points, float))


def test_samples_have_no_failures_except_the_t5_aluminium_pipe():
    for p in SAMPLES.values():
        rep = check_part(p)
        if p.part_no == "PF-CP-1610":
            fails = [c for c in rep.checks if c.status == FAIL]
            assert [c.rule for c in fails] == ["D8"]
            assert "softer temper" in fails[0].detail and "100 mm" in fails[0].detail
        else:
            assert rep.status in (PASS, WARN), p.part_no


def test_small_steel_tube_needs_elongation_in_the_purchase_spec():
    d8 = next(c for c in check_part(SAMPLES["PF-HB-2201"]).checks if c.rule == "D8")
    assert d8.status == WARN and "purchase specification" in d8.detail and "18.5%" in d8.detail


def test_d1_bands_follow_the_sources():
    def d1(clr):
        p = _part([[0, 0, 0], [200, 0, 0], [200, 200, 0]], clr=clr)  # OD 20
        return next(c for c in check_part(p).checks if c.rule == "D1")

    assert d1(10.0).status == FAIL  # 0.5D
    ultra = d1(15.0)  # 0.75D
    assert ultra.status == WARN and "0.6D" in ultra.detail
    assert d1(25.0).status == WARN  # 1.25D extreme
    assert d1(60.0).status == PASS and "optimal" in d1(60.0).detail


def test_clamp_and_distance_between_bends_rules():
    assert clamp_length(20.0, 40.0) == 60.0  # 5 OD - CLR
    assert clamp_length(20.0, 90.0) == 40.0  # not less than 2 OD
    assert clamp_length(20.0, 90.0, serrated=True) == 20.0
    assert min_between_bends(20.0, 40.0) == 80.0  # D = 2: 4 OD
    assert min_between_bends(20.0, 60.0) == 60.0  # D = 3: 3 OD


def test_short_straight_between_bends_warns_then_fails():
    def three(gap):
        # two 90 deg bends at CLR 40 on OD 20 (2D): need max(60 clamp, 80 Pines) = 80 mm
        t = 40.0
        return _part([[0, 0, 0], [200, 0, 0], [200, 2 * t + gap, 0], [400, 2 * t + gap, 0]], clr=40.0)

    assert any(c.rule == "D3" and c.status == WARN for c in check_part(three(60)).checks)
    assert any(c.rule == "D3" and c.status == FAIL for c in check_part(three(30)).checks)
    assert all(c.status == PASS for c in check_part(three(90)).checks if c.rule == "D3")


def test_short_leading_end_asks_for_extra_stock():
    p = _part([[0, 0, 0], [50, 0, 0], [50, 300, 0]], clr=40.0)  # leading straight 10 mm
    lead = next(c for c in check_part(p).checks if c.title == "Leading end")
    assert lead.status == WARN and "add 30 mm clamping stock" in lead.detail


def test_chart_lookup_and_shifts():
    t = tooling_for(od=50.0, wall=1.0, clr=75.0)  # WF 50 at 1.5D
    assert t["code"] == "R3W" and t["zone"] == 2 and "3-ball" in t["mandrel"]
    assert tooling_for(od=20.0, wall=2.5, clr=60.0)["code"] == "NNN"  # WF 8 at 3D
    # Tube Form Solutions example: 2.00 OD x .065 wall stainless at 4 in CLR needs a 2-ball mandrel and a wiper
    ex = tooling_for(od=2.0, wall=0.065, clr=4.0, material="SUS304")
    assert ex["code"] == "R2W" and ex["notes"]
    assert tooling_for(od=50.0, wall=1.0, clr=75.0, angle_deg=30.0)["col"] == 2.0  # under 45 deg: one right
    assert tooling_for(od=20.0, wall=1.0, clr=10.0)["zone"] == 4  # 0.5D, off the chart


def test_ovality_estimate_tube_form_solutions_rule():
    # 2.00 OD, .065 wall, 4.0 CLR: difficulty factor 15.4, ovality about 0.7 x 15.4
    assert ovality_estimate(2.0, 0.065, 4.0) == pytest.approx(0.7 * (2.0 / 0.065) / 2.0)


def test_self_intersecting_part_fails_d7():
    # a closed-ish loop: the tube comes back across its own start
    pts = [[0, 0, 0], [300, 0, 0], [300, 150, 0], [150, 150, 0], [150, -150, 0]]
    rep = check_part(_part(pts, clr=30.0))
    assert any(c.rule == "D7" and c.status == FAIL for c in rep.checks)


def test_collision_scan_finds_a_part_swinging_into_the_floor():
    # bend 1 makes a 1.5 m leg, then a 90 deg out-of-plane rotation swings that leg below the axis
    rows = (LRARow(L=1500.0, R=0.0, A=90.0, clr=40.0), LRARow(L=100.0, R=90.0, A=90.0, clr=40.0))
    lra = LRA(rows=rows, final_L=200.0)
    hits = collision_scan(lra, 20.0, Machine())
    hits_r = collision_scan(LRA(rows=(rows[0], LRARow(L=100.0, R=-90.0, A=90.0, clr=40.0)), final_L=200.0), 20.0,
                            Machine())
    assert any(h["with"] == "floor" for h in hits + hits_r)


def test_a_flat_part_bent_in_plane_never_hits_the_floor():
    p = SAMPLES["PF-HB-2201"]
    assert not [h for h in collision_scan(p.lra(), p.od, Machine()) if h["with"] == "floor"]


def test_oversize_tube_fails():
    p = _part([[0, 0, 0], [200, 0, 0], [200, 200, 0]], clr=120.0, od=60.0, wall=3.0)
    assert check_part(p).status == FAIL


def test_report_rows_are_serialisable():
    import json

    rep = check_part(SAMPLES["PF-FT-2541"])
    json.dumps(rep.as_rows())
    assert sum(rep.counts().values()) == len(rep.checks)


def test_xyz_from_program_matches_for_problem_parts():
    pts = np.array([[0, 0, 0], [200, 0, 0], [200, 120, 50]], float)
    assert np.abs(lra_to_xyz(xyz_to_lra(pts, 40.0)) - pts).max() < 1e-9


def test_every_material_value_has_a_source_url():
    for m in MATERIALS.values():
        assert m.sources and all("http" in v for v in m.sources.values()), m.grade


def test_material_values_match_the_jis_tables():
    assert MATERIALS["STKM11A"].yield_mpa is None and MATERIALS["STKM11A"].tensile_mpa == 290
    assert (MATERIALS["STKM13A"].yield_mpa, MATERIALS["STKM13A"].tensile_mpa) == (215, 370)
    assert (MATERIALS["SUS304"].yield_mpa, MATERIALS["SUS304"].tensile_mpa) == (205, 520)
    assert MATERIALS["A6063-T5"].tensile_mpa == 155  # tube standard H 4080, not the 150 of H 4100
