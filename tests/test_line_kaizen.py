import pytest

from pipeforge import kaizen
from pipeforge.line_sim import LineSpec, baseline_line, capacity_per_day, replicate, simulate, yamazumi


def test_takt_is_available_time_over_demand():
    line = baseline_line()
    assert line.available_s_per_day == 2 * (480 - 60) * 60
    assert line.takt_s == pytest.approx(50_400 / 1500)


def test_simulation_never_beats_the_bottleneck_capacity():
    line = baseline_line()
    cap = min(capacity_per_day(line).values())
    for seed in range(3):
        assert simulate(line, days=3, seed=seed).per_day <= cap * 1.02  # 2 % for randomness over 3 days


def test_same_seed_same_result_different_seed_different():
    line = baseline_line()
    a, b, c = (simulate(line, days=1, seed=s) for s in (7, 7, 8))
    assert a.finished_good == b.finished_good
    assert a.finished_good != c.finished_good


def test_oee_is_availability_times_performance_times_quality():
    line = baseline_line()
    run = simulate(line, days=2, seed=1)
    for key, o in run.oee_table().items():
        st = run.stations[key]
        assert o["oee"] == pytest.approx(o["availability"] * o["performance"] * o["quality"])
        assert o["oee"] == pytest.approx(st.good * line.station(key).cycle_s / run.planned_s)
        assert 0 <= o["oee"] <= 1.0


def test_flow_is_conserved():
    run = simulate(baseline_line(), days=1, seed=3)
    keys = [s.key for s in run.line.stations]
    for i, (up, down) in enumerate(zip(keys, keys[1:], strict=False)):
        moved = run.stations[up].good
        # a good part upstream is either processed downstream, in the buffer, waiting to enter a full
        # buffer (blocked hand-off), or being worked on downstream when the run stops
        assert run.stations[down].processed <= moved
        assert moved - run.stations[down].processed <= run.line.buffers[i] + 2


def test_latent_bend_defects_are_scrapped_at_inspection_not_at_bending():
    line = baseline_line().with_station("BEND", latent_fpy=0.5, fpy=1.0)
    run = simulate(line, days=1, seed=2)
    assert run.stations["BEND"].scrapped == 0
    assert run.stations["INSP"].scrapped > 0.3 * run.stations["INSP"].processed


def test_perfect_line_without_losses_runs_at_its_slowest_station():
    base = baseline_line()
    from dataclasses import replace

    stations = tuple(replace(s, cv=0.0, mtbf_min=0.0, changeover_min=0.0, fpy=1.0, latent_fpy=1.0) for s in base.stations)
    line = replace(base, stations=stations, buffers=(50,) * 5)
    run = simulate(line, days=1, seed=0)
    slowest = max(s.cycle_s for s in stations)
    assert run.per_day == pytest.approx(line.available_s_per_day / slowest, rel=0.01)


def test_buffer_count_must_match():
    with pytest.raises(ValueError):
        LineSpec(stations=baseline_line().stations, buffers=(1, 2), demand_per_day=100)


def test_rebalancing_moves_work_without_losing_any():
    before = baseline_line()
    after = kaizen.rebalance(before)
    assert sum(s.cycle_s for s in after.stations) == sum(s.cycle_s for s in before.stations)
    assert after.station("END").cycle_s < before.takt_s
    assert max(s.cycle_s for s in after.stations) < before.takt_s


def test_smed_moves_steps_outside_and_shortens_internal_time():
    rows, before, after = kaizen.smed_table()
    assert before == sum(r["minutes_before"] for r in rows if r["internal_before"])
    assert after == sum(r["minutes_after"] for r in rows if r["internal_after"])
    assert after < before
    assert kaizen.smed(baseline_line()).station("BEND").changeover_min == after


def test_knee_is_the_smallest_buffer_within_one_percent_of_the_best():
    curve = [{"buffer": 1, "per_day": 90}, {"buffer": 2, "per_day": 99.5}, {"buffer": 3, "per_day": 100}]
    assert kaizen.knee(curve) == 2


def test_rebalancing_raises_throughput():
    base = replicate(baseline_line(), reps=3, days=2)
    reb = replicate(kaizen.rebalance(baseline_line()), reps=3, days=2)
    assert reb["per_day"].mean > base["per_day"].mean


def test_yamazumi_rows_sum_to_cycle_times():
    line = baseline_line()
    rows = yamazumi(line)
    for s in line.stations:
        assert sum(r["seconds"] for r in rows if r["station"] == s.key) == s.cycle_s
