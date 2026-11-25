# A3 kaizen report: bent-tube cell (cut, end form, bend, TIG weld, inspect, pack)

> **Scope and honesty:** the line is a **synthetic SimPy model** with illustrative cycle times, failures and yields. It is not a real plant. The only real-data input is the bending yield in countermeasure 4, which comes from 315 real TubeBEND bends. Every number below is from `python -m pipeforge.kaizen`: 10 replications × 5 days per scenario, common random numbers, with the 95% confidence half-width shown.

## 1. Background (背景)

The cell must deliver **1,500 good parts/day** in 2 shifts × 420 min, so **takt = 33.6 s**. It currently delivers about two thirds of that. Bends that are out of tolerance are found only at the checking fixture, so each one has already used TIG-welding capacity.

## 2. Current condition (現状)

| Metric | Baseline |
|---|---|
| Good parts/day | **940 ± 10** (62.7% of demand) |
| Scrap | 13.8% |
| WIP (buffers) | 12.4 parts |
| Bottleneck | End forming (37 s against a 33.6 s takt) |
| Bender OEE | 0.579 |
| Bender changeover | 25 min, all internal |
| Bends within ±0.5° | 88.3% (one constant springback offset for every setup) |

**Yamazumi:** end forming carries 37 s of work, 4 s over takt. The saw has 16 s, so roughly half its takt time is spare.

## 3. Target (目標)

Meet demand without adding machines or people:
- at least 1,400 good parts/day;
- scrap below 5%.

## 4. Root cause (要因解析)

**5 Whys** on "the line misses demand":
1. Not enough good parts leave packing. Why?
2. End forming cannot keep up, and scrap at inspection wastes capacity upstream. Why?
3. End forming has more work than takt, and many bends are out of tolerance. Why?
4. Deburring sits at end forming. Springback is corrected with one fixed offset for every setup. Why?
5. The work split was never rebalanced against takt, and nobody re-teaches springback after a changeover, because trial bends cost changeover time.

**Fishbone (summary):**

| Branch | Cause |
|---|---|
| Method | Unbalanced work; long internal changeover |
| Machine | Bender breakdowns, MTBF 240 min |
| Material | Springback varies with setup (TubeBEND: 2.60° ± 0.28°) |
| Measurement | Defects found late, at the fixture |
| Man | Changeover steps not standardised |

## 5. Countermeasures (対策) and results (効果)

| # | Countermeasure | Good parts/day | Scrap | Bottleneck | Bender OEE |
|---|---|---|---|---|---|
| 0 | Baseline | 940 ± 10 | 13.8% | End forming | 0.579 |
| 1 | **Line rebalancing**: move deburring (9 s) from end forming to the saw; no station now exceeds takt | 1,132 ± 16 | 13.9% | Bender | 0.698 |
| 2 | **SMED on the bender**: internal changeover 25 to 10 min | 1,226 ± 18 | 13.9% | End forming | 0.756 |
| 3 | **Buffer sizing**: end-form-to-bender buffer 10 to 17 parts (knee of the curve) | 1,247 ± 18 | 13.9% | End forming | 0.768 |
| 4 | **Closed-loop springback compensation** (ML, real data): bends within ±0.5° from 88.3% to 99.7% | **1,396 ± 19** | **2.9%** | End forming | 0.762 |

**Overall: +48.5% good parts/day (940 to 1,396) and −10.9 percentage points of scrap.** That is 93.1% of demand.

**SMED detail** (synthetic times):

| Step | Before | After |
|---|---|---|
| Fetch die set and clamp die from store | internal | external, done while running |
| Load program and springback values | internal | external |
| Fit and align die set | 6 min | 2 min (locating pins, quick-release bolts) |
| Change mandrel and wiper die | 4 min | 2 min (preset rod length) |
| Trial bends and fixture check | 3 min | 2 min (sensor fixture, ML offset) |
| **Internal total** | **25 min** | **10 min** |

**Buffer curve.** Throughput rises slowly from 1,173 parts/day at a buffer of 1 to about 1,250 at 17–20. The knee was taken at 17, within 1% of the best seen. This step is the smallest gain (+21 parts/day) and costs WIP (+5 parts). In a real plant it would be the first one to question.

## 6. Follow-up (今後の課題)

- **Demand is still missed by 7%.** End forming is again the constraint. Next steps: a SMED study on the end-forming die, and checking whether its 12-minute changeover can drop below 5.
- **Validate the springback model on our own tooling** before trusting it. It is trained only on the TubeBEND tube; a real deployment needs its own trial data.
- **Watch the bender's MTBF.** At 240 min it is the next availability loss.

## 7. Yokoten (横展開)

Roll out the three countermeasures that do not depend on this part:
- **Takt-based rebalancing.** Use the Yamazumi template (`line_sim.yamazumi`) on every cell.
- **SMED.** Apply the external/internal changeover checklist (`kaizen.SMED_STEPS`) to every bender.
- **Sensor checking fixture.** Use the same generator (`fixture.py`) and station logic (`station.py`) for the other part numbers.

The springback model is spread only where the tube, material and tooling match. Elsewhere, the same pipeline is used to collect the data first.
