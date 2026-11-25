"""Discrete-event model of a bent-tube cell: cut, end form, bend, TIG weld, inspect, pack.

**All line parameters are synthetic.** Cycle times, failure rates, changeover
times and yields are illustrative values chosen to be plausible for a small
tube cell, not data from Yamato or any other plant. The only real-data input
is the bending first-pass yield in the closed-loop kaizen scenario, which
comes from the springback model on TubeBEND (see kaizen.py).

Model (SimPy, time in seconds):

* Raw tube is always available at the saw; finished parts leave from packing.
* Stations are joined by finite buffers; a station that finishes a part into
  a full buffer is *blocked*, one waiting for a part is *starved*.
* Cycle times are lognormal around the sum of the station's work elements.
* Breakdowns arrive while the station runs (exponential time to failure,
  mean MTBF) and take an exponential repair time (mean MTTR).
* A changeover is taken every ``batch_size`` parts at stations with one
  (product mix on shared equipment).
* A station's own yield scraps parts on the spot. Bending defects are
  *latent*: an out-of-tolerance bend is only found at the checking fixture,
  after it has used TIG-welding capacity.

OEE per station follows Nakajima's definition, OEE = availability x
performance x quality, which equals good output x ideal cycle time / planned
time (ENGINEERING_NOTES, section 6).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace

import numpy as np
import simpy


@dataclass(frozen=True)
class Element:
    name: str
    seconds: float
    kind: str  #: "manual", "machine" or "walk"


@dataclass(frozen=True)
class StationSpec:
    key: str
    name: str
    name_ja: str
    elements: tuple[Element, ...]
    cv: float = 0.08  #: coefficient of variation of the cycle time
    mtbf_min: float = 0.0  #: mean run time between failures; 0 = never fails
    mttr_min: float = 0.0
    changeover_min: float = 0.0  #: per product change
    fpy: float = 1.0  #: first-pass yield; failures are scrapped here
    latent_fpy: float = 1.0  #: defects found only at inspection (bending)
    inspects: bool = False  #: removes parts with latent defects

    @property
    def cycle_s(self) -> float:
        return sum(e.seconds for e in self.elements)

    def work(self, kind: str) -> float:
        return sum(e.seconds for e in self.elements if e.kind == kind)


@dataclass(frozen=True)
class LineSpec:
    stations: tuple[StationSpec, ...]
    buffers: tuple[int, ...]  #: capacity after each station except the last
    demand_per_day: int
    shifts: int = 2
    shift_min: float = 480.0
    break_min: float = 60.0  #: planned stops per shift (breaks, meetings, 5S)
    batch_size: int = 300  #: parts per product run before a changeover

    def __post_init__(self) -> None:
        if len(self.buffers) != len(self.stations) - 1:
            raise ValueError("need one buffer between each pair of stations")

    @property
    def available_s_per_day(self) -> float:
        return self.shifts * (self.shift_min - self.break_min) * 60.0

    @property
    def takt_s(self) -> float:
        """Takt time = available production time / customer demand."""
        return self.available_s_per_day / self.demand_per_day

    def station(self, key: str) -> StationSpec:
        return next(s for s in self.stations if s.key == key)

    def with_station(self, key: str, **changes) -> LineSpec:  # type: ignore[no-untyped-def]
        return replace(self, stations=tuple(replace(s, **changes) if s.key == key else s for s in self.stations))


@dataclass
class StationStats:
    key: str
    processed: int = 0
    good: int = 0
    scrapped: int = 0
    busy_s: float = 0.0
    down_s: float = 0.0
    changeover_s: float = 0.0
    starved_s: float = 0.0
    blocked_s: float = 0.0
    failures: int = 0

    def oee(self, planned_s: float, ideal_ct: float) -> dict[str, float]:
        run = planned_s - self.down_s - self.changeover_s
        a = run / planned_s if planned_s else 0.0
        p = (ideal_ct * self.processed) / run if run > 0 else 0.0
        q = self.good / self.processed if self.processed else 0.0
        return {"availability": a, "performance": p, "quality": q, "oee": a * p * q}


@dataclass
class RunResult:
    days: float
    finished_good: int
    started: int
    stations: dict[str, StationStats]
    wip_mean: float
    lead_time_s: float
    planned_s: float
    line: LineSpec

    @property
    def per_day(self) -> float:
        return self.finished_good / self.days

    def scrap_pct(self) -> float:
        scrapped = sum(s.scrapped for s in self.stations.values())
        return 100.0 * scrapped / self.started if self.started else 0.0

    def oee_table(self) -> dict[str, dict[str, float]]:
        return {k: s.oee(self.planned_s, self.line.station(k).cycle_s) for k, s in self.stations.items()}

    def bottleneck(self) -> str:
        """Station with the highest share of time busy, down or in changeover (least idle)."""
        def util(s: StationStats) -> float:
            return (s.busy_s + s.down_s + s.changeover_s) / self.planned_s

        return max(self.stations.values(), key=util).key


def _lognormal(rng: np.random.Generator, mean: float, cv: float) -> float:
    if cv <= 0:
        return mean
    s2 = math.log(1.0 + cv * cv)
    return float(rng.lognormal(math.log(mean) - s2 / 2.0, math.sqrt(s2)))


def simulate(line: LineSpec, days: float = 5.0, seed: int = 0, warmup_parts: int = 0) -> RunResult:
    """Run the line for *days* of planned production time."""
    rng = np.random.default_rng(seed)
    env = simpy.Environment()
    n = len(line.stations)
    stores = [simpy.Store(env, capacity=c) for c in line.buffers] + [simpy.Store(env)]
    stats = {s.key: StationStats(s.key) for s in line.stations}
    started = [0]
    wip_samples: list[int] = []
    lead_times: list[float] = []
    horizon = days * line.available_s_per_day

    def station(idx: int):  # type: ignore[no-untyped-def]
        spec = line.stations[idx]
        st = stats[spec.key]
        up = stores[idx - 1] if idx > 0 else None
        down = stores[idx]
        since_change = 0
        while True:
            t0 = env.now
            if up is None:
                part = {"t0": env.now, "latent_ok": True}
                started[0] += 1
            else:
                part = yield up.get()
            st.starved_s += env.now - t0
            if spec.changeover_min > 0 and since_change >= line.batch_size:
                co = spec.changeover_min * 60.0
                yield env.timeout(co)
                st.changeover_s += co
                since_change = 0
            work = _lognormal(rng, spec.cycle_s, spec.cv)
            while work > 1e-9:
                if spec.mtbf_min > 0:
                    ttf = float(rng.exponential(spec.mtbf_min * 60.0))
                    if ttf < work:
                        yield env.timeout(ttf)
                        st.busy_s += ttf
                        work -= ttf
                        rep = float(rng.exponential(spec.mttr_min * 60.0))
                        yield env.timeout(rep)
                        st.down_s += rep
                        st.failures += 1
                        continue
                yield env.timeout(work)
                st.busy_s += work
                work = 0.0
            st.processed += 1
            since_change += 1
            if rng.random() > spec.fpy:
                st.scrapped += 1
                continue
            if spec.latent_fpy < 1.0 and rng.random() > spec.latent_fpy:
                part["latent_ok"] = False
            if spec.inspects and not part["latent_ok"]:
                st.scrapped += 1
                continue
            st.good += 1
            t1 = env.now
            yield down.put(part)
            st.blocked_s += env.now - t1
            if idx == n - 1:
                lead_times.append(env.now - part["t0"])

    def sampler():  # type: ignore[no-untyped-def]
        while True:
            wip_samples.append(sum(len(s.items) for s in stores[:-1]))
            yield env.timeout(60.0)

    for i in range(n):
        env.process(station(i))
    env.process(sampler())
    env.run(until=horizon)
    return RunResult(
        days=days,
        finished_good=len(stores[-1].items),
        started=started[0],
        stations=stats,
        wip_mean=float(np.mean(wip_samples)) if wip_samples else 0.0,
        lead_time_s=float(np.mean(lead_times)) if lead_times else float("nan"),
        planned_s=horizon,
        line=line,
    )


@dataclass
class Summary:
    """Mean and spread of a metric over independent replications."""

    mean: float
    sd: float
    n: int
    values: list[float] = field(default_factory=list)

    @property
    def ci95(self) -> float:
        """Half-width of a 95 % confidence interval (t with n-1 df, n >= 2)."""
        t = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 8: 2.36, 10: 2.26, 12: 2.20, 15: 2.14, 20: 2.09, 30: 2.05}
        k = min(t, key=lambda x: abs(x - self.n))
        return t[k] * self.sd / math.sqrt(self.n) if self.n > 1 else float("nan")


def summarize(values: list[float]) -> Summary:
    return Summary(statistics.fmean(values), statistics.stdev(values) if len(values) > 1 else 0.0, len(values), values)


def replicate(line: LineSpec, reps: int = 10, days: float = 5.0, seed0: int = 1000) -> dict:
    """Run *reps* independent replications (common random-number seeds across scenarios)."""
    runs = [simulate(line, days=days, seed=seed0 + r) for r in range(reps)]
    oee_keys = [s.key for s in line.stations]
    return {
        "runs": runs,
        "per_day": summarize([r.per_day for r in runs]),
        "scrap_pct": summarize([r.scrap_pct() for r in runs]),
        "wip": summarize([r.wip_mean for r in runs]),
        "lead_time_min": summarize([r.lead_time_s / 60.0 for r in runs]),
        "oee": {k: summarize([r.oee_table()[k]["oee"] for r in runs]) for k in oee_keys},
        "bottleneck": max(set(r.bottleneck() for r in runs), key=[r.bottleneck() for r in runs].count),
    }


def capacity_per_day(line: LineSpec) -> dict[str, float]:
    """Deterministic upper bound on good output per day for each station alone.

    Each station's rate is limited by its mean cycle time, its expected
    breakdown time per part (cycle / MTBF * MTTR), and its changeover time
    shared over a batch; then by every yield loss from that station onwards.
    The line can never beat the smallest of these, which the tests check.
    """
    out: dict[str, float] = {}
    for i, s in enumerate(line.stations):
        per_part = s.cycle_s
        if s.mtbf_min > 0:
            per_part += s.cycle_s / (s.mtbf_min * 60.0) * s.mttr_min * 60.0
        if s.changeover_min > 0:
            per_part += s.changeover_min * 60.0 / (line.batch_size + 1)
        rate = line.available_s_per_day / per_part
        for t in line.stations[i:]:
            rate *= t.fpy
        latent = math.prod(t.latent_fpy for t in line.stations[: i + 1]) if any(
            t.inspects for t in line.stations[i:]) else 1.0
        out[s.key] = rate * latent
    return out


def yamazumi(line: LineSpec) -> list[dict]:
    """Stacked work content per station, for the Yamazumi chart."""
    rows = []
    for s in line.stations:
        for e in s.elements:
            rows.append({"station": s.key, "name": s.name, "element": e.name, "kind": e.kind, "seconds": e.seconds})
    return rows


def baseline_line() -> LineSpec:
    """The synthetic baseline cell used throughout the docs (all values illustrative)."""
    return LineSpec(
        stations=(
            StationSpec("CUT", "Cut-off saw", "切断",
                        (Element("load bar stock", 3, "manual"), Element("cut to length", 9, "machine"),
                         Element("unload and stack", 4, "manual")),
                        mtbf_min=600, mttr_min=8, changeover_min=5),
            StationSpec("END", "End forming", "端末加工",
                        (Element("load", 4, "manual"), Element("deburr and chamfer ends", 9, "manual"),
                         Element("flare and bead", 14, "machine"), Element("unload and check", 6, "manual"),
                         Element("walk to rack", 4, "walk")),
                        mtbf_min=400, mttr_min=10, changeover_min=12, fpy=0.995),
            StationSpec("BEND", "CNC rotary-draw bending", "曲げ",
                        (Element("load to collet", 5, "manual"), Element("bend cycle", 18, "machine"),
                         Element("unload", 4, "manual")),
                        mtbf_min=240, mttr_min=12, changeover_min=25, fpy=0.995, latent_fpy=0.90),
            StationSpec("WELD", "TIG weld bracket", "TIG溶接",
                        (Element("load weld jig", 5, "manual"), Element("TIG weld bracket", 16, "manual"),
                         Element("unload", 4, "manual")),
                        mtbf_min=480, mttr_min=10, changeover_min=10, fpy=0.985),
            StationSpec("INSP", "Checking fixture", "検査",
                        (Element("load to fixture", 4, "manual"), Element("sensor check", 6, "machine"),
                         Element("unload and label", 4, "manual")),
                        inspects=True),
            StationSpec("PACK", "Packing", "梱包",
                        (Element("pack", 8, "manual"), Element("walk to pallet", 2, "walk"))),
        ),
        buffers=(10, 10, 2, 10, 10),
        demand_per_day=1500,
    )
