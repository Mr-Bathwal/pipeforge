"""Kaizen scenarios on the synthetic line: before and after numbers from the simulation.

Scenarios are applied cumulatively, in the order a team would usually take
them, and every scenario is run with the same random-number seeds (common
random numbers), so the differences come from the change and not from noise:

1. **Line rebalancing.** Move deburring from end forming (over takt) to the
   saw (which has slack), so no station exceeds takt (Yamazumi).
2. **SMED on the bender.** Convert internal changeover steps to external ones
   (pre-staged die set, preset program, quick-release clamp die).
3. **Buffer sizing.** Size the buffer in front of the bender, now the
   constraint, at the knee of the throughput curve.
4. **Closed-loop springback compensation.** The baseline bending yield is
   the share of real TubeBEND runs inside +/-0.5 deg with one constant
   offset for every setup; the scenario raises it to the share the
   setup-aware ML model achieves (both out-of-fold, from M3). Skipped, not
   guessed, if M3 has not been run.

Run ``python -m pipeforge.kaizen`` to regenerate artifacts/line/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from .line_sim import Element, LineSpec, baseline_line, replicate

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "line"
CLOSED_LOOP = ROOT / "artifacts" / "springback" / "closed_loop.json"

REPS = 10
DAYS = 5.0

#: SMED study of the bender changeover (synthetic times, minutes). (step, minutes, internal before, internal after)
SMED_STEPS: tuple[tuple[str, float, bool, bool], ...] = (
    ("Fetch next bend die set and clamp die from store", 5.0, True, False),
    ("Remove bend die, clamp die, pressure die", 4.0, True, True),
    ("Fit and align next die set", 6.0, True, True),
    ("Load bending program and enter springback values", 3.0, True, False),
    ("Change mandrel and wiper die", 4.0, True, True),
    ("Trial bends and measure on checking fixture", 3.0, True, True),
)
#: improvements applied to internal steps that stay internal (minutes saved)
SMED_INTERNAL_GAINS = {
    "Fit and align next die set": 4.0,  # locating pins and quick-release bolts
    "Change mandrel and wiper die": 2.0,  # pre-set mandrel rod length
    "Trial bends and measure on checking fixture": 1.0,  # first-article check on the sensor fixture
}


def smed_table() -> tuple[list[dict], float, float]:
    rows = []
    before = after = 0.0
    for step, minutes, int_before, int_after in SMED_STEPS:
        new_min = minutes - SMED_INTERNAL_GAINS.get(step, 0.0)
        rows.append({"step": step, "minutes_before": minutes, "internal_before": int_before,
                     "minutes_after": new_min, "internal_after": int_after})
        before += minutes if int_before else 0.0
        after += new_min if int_after else 0.0
    return rows, before, after


def rebalance(line: LineSpec) -> LineSpec:
    end = line.station("END")
    cut = line.station("CUT")
    moved = next(e for e in end.elements if e.name == "deburr and chamfer ends")
    new_end = tuple(e for e in end.elements if e is not moved)
    new_cut = (*cut.elements[:-1], Element(moved.name, moved.seconds, moved.kind), cut.elements[-1])
    return line.with_station("END", elements=new_end).with_station("CUT", elements=new_cut)


def smed(line: LineSpec) -> LineSpec:
    _, _, after = smed_table()
    return line.with_station("BEND", changeover_min=after)


def buffer_curve(line: LineSpec, sizes: range = range(1, 21), reps: int = REPS, days: float = DAYS) -> list[dict]:
    idx = [s.key for s in line.stations].index("BEND") - 1
    out = []
    for n in sizes:
        b = list(line.buffers)
        b[idx] = n
        r = replicate(replace(line, buffers=tuple(b)), reps=reps, days=days)
        out.append({"buffer": n, "per_day": r["per_day"].mean, "sd": r["per_day"].sd, "wip": r["wip"].mean})
    return out


def knee(curve: list[dict], within: float = 0.01) -> int:
    """Smallest buffer whose throughput is within *within* of the best."""
    best = max(c["per_day"] for c in curve)
    return min(c["buffer"] for c in curve if c["per_day"] >= (1.0 - within) * best)


def set_buffer(line: LineSpec, n: int) -> LineSpec:
    idx = [s.key for s in line.stations].index("BEND") - 1
    b = list(line.buffers)
    b[idx] = n
    return replace(line, buffers=tuple(b))


@dataclass
class ScenarioResult:
    name: str
    line: LineSpec
    stats: dict
    note: str = ""

    def row(self) -> dict:
        s = self.stats
        bend = self.line.station("BEND")
        return {
            "scenario": self.name,
            "per_day": round(s["per_day"].mean, 1),
            "per_day_sd": round(s["per_day"].sd, 1),
            "per_day_ci95": round(s["per_day"].ci95, 1),
            "demand_met_pct": round(100.0 * s["per_day"].mean / self.line.demand_per_day, 1),
            "scrap_pct": round(s["scrap_pct"].mean, 2),
            "wip": round(s["wip"].mean, 1),
            "lead_time_min": round(s["lead_time_min"].mean, 1),
            "bottleneck": s["bottleneck"],
            "oee_bend": round(s["oee"]["BEND"].mean, 3),
            "max_station_ct_s": max(st.cycle_s for st in self.line.stations),
            "takt_s": round(self.line.takt_s, 2),
            "bend_changeover_min": bend.changeover_min,
            "bend_latent_fpy": bend.latent_fpy,
            "note": self.note,
        }


def closed_loop_fpy() -> dict | None:
    if not CLOSED_LOOP.exists():
        return None
    return json.loads(CLOSED_LOOP.read_text(encoding="utf-8"))


def run_all(reps: int = REPS, days: float = DAYS) -> dict:
    results: list[ScenarioResult] = []
    line = baseline_line()
    cl = closed_loop_fpy()
    if cl is not None:
        # Baseline: one constant springback offset carried across setups (no re-teach after changeover).
        # The per-bend yield is applied to the part as if it had one critical bend; a part with n
        # independent bends would see yield**n, so this mapping understates the gain on purpose.
        line = line.with_station("BEND", latent_fpy=cl["fpy"][cl["baseline_policy"]])
    results.append(ScenarioResult("0 Baseline", line, replicate(line, reps, days)))

    line = rebalance(line)
    results.append(ScenarioResult("1 Line rebalancing", line, replicate(line, reps, days),
                                  "deburring moved from end forming to the saw"))
    _, co_before, co_after = smed_table()
    line = smed(line)
    results.append(ScenarioResult("2 SMED on bender", line, replicate(line, reps, days),
                                  f"bender changeover {co_before:g} to {co_after:g} min internal"))
    curve = buffer_curve(line, reps=reps, days=days)
    k = knee(curve)
    line = set_buffer(line, k)
    results.append(ScenarioResult("3 Buffer before bender", line, replicate(line, reps, days),
                                  f"buffer {baseline_line().buffers[1]} to {k} parts (knee of curve)"))
    if cl is not None:
        line = line.with_station("BEND", latent_fpy=cl["fpy"]["ml"])
        results.append(ScenarioResult("4 Closed-loop springback", line, replicate(line, reps, days),
                                      "bend yield from ML compensation on real TubeBEND runs"))
    rows = [r.row() for r in results]
    base, last = rows[0], rows[-1]
    return {
        "reps": reps,
        "days": days,
        "synthetic": True,
        "rows": rows,
        "buffer_curve": curve,
        "smed": smed_table()[0],
        "throughput_gain_pct": round(100.0 * (last["per_day"] - base["per_day"]) / base["per_day"], 1),
        "scrap_change_pts": round(last["scrap_pct"] - base["scrap_pct"], 2),
        "closed_loop_source": str(CLOSED_LOOP.relative_to(ROOT)) if cl is not None else None,
        "lines": {r.name: r.line for r in results},
    }


def main() -> None:
    from .line_sim import yamazumi

    OUT.mkdir(parents=True, exist_ok=True)
    res = run_all()
    lines = res.pop("lines")
    res["yamazumi_before"] = yamazumi(baseline_line())
    res["yamazumi_after"] = yamazumi(list(lines.values())[-1])
    (OUT / "kaizen_results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["| Scenario | Good parts/day (mean +/- 95% CI) | Demand met | Scrap % | WIP | Bottleneck | Bender OEE |",
          "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        md.append(f"| {r['scenario']} | {r['per_day']:.0f} +/- {r['per_day_ci95']:.0f} | {r['demand_met_pct']:.1f}% | "
                  f"{r['scrap_pct']:.2f} | {r['wip']:.1f} | {r['bottleneck']} | {r['oee_bend']:.3f} |")
    md.append("")
    md.append(f"Synthetic line, {res['reps']} replications x {res['days']:g} days each, common random numbers.")
    md.append(f"Throughput change, baseline to last scenario: {res['throughput_gain_pct']:+.1f}%. "
              f"Scrap change: {res['scrap_change_pts']:+.2f} percentage points.")
    (OUT / "kaizen_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
