# Line transfer playbook: replicating the bent-tube cell in a new plant

This is written for the expatriate assignment in the Yamato listing: setting up a copy of a proven cell in a plant outside Japan. Yamato's public site lists overseas production in Vietnam and Indonesia; the listing names India. **It is a study plan written from public lean and quality practice, not experience of a real transfer.** Each step names the PipeForge output it would use.

## 0. Principle

**Copy the standard, then improve it locally.** First reproduce the mother line's numbers: takt, cycle times, first-pass yield. Change things only after that (yokoten in reverse: learn from the mother plant first).

## 1. Before shipping equipment (in Japan)

| Item | Output |
|---|---|
| Part data pack per part number: XYZ, LRA, compensated YBC, drawing, process sheet | `artifacts/parts/<part>/` |
| Machine and tooling list per part (bend die, clamp die, mandrel, wiper) from the chart | DFM report, rule D2 |
| Checking fixture plus master part, shipped with a calibration record | `fixture.py` output |
| Line model with the mother plant's measured cycle times; target takt for the new plant's demand | `line_sim.py` |
| Material purchase specification **including minimum elongation** (JIS does not guarantee it at 40 mm OD or less) | DFM rule D8 |

## 2. Standard work and training

- **Standard work sheet per station:** work elements and times (from the Yamazumi data), key points, safety, quality checks.
- **Training matrix (星取表, skills map):**
  - each operator × each station, at levels 1–4;
  - target: at least 3 trained operators per station before start of production.
- **Order of training:**
  1. checking fixture and station (simplest, and teaches the quality standard first);
  2. saw and packing;
  3. end forming;
  4. TIG welding (needs welder qualification to the WPS);
  5. bending, with changeover and springback re-teach.
- Trainers from the mother plant work alongside local leaders. Local leaders then train the next shift.

## 3. Start-up checks

1. **Machine acceptance.**
   - Bender repeatability: bend the same program 10 times and check on the fixture.
   - Check the axis positions against the program.
2. **First-article inspection** per part number: the full drawing check, including bend table, cut length and ends.
3. **Gauge R&R** of the checking fixture: 10 parts × 3 operators × 2 trials. Target %GRR below 10%; accept up to 30% only with a plan.
4. **Springback data.** Run trial bends per setup. Compare with the shipped values, or retrain the model if the tube, material or tooling differ. The TubeBEND model is not valid on a new machine without new data.
5. **Short run at reduced rate, then the full rate.** Compare the good-parts/day trend with the line model's prediction.

## 4. Daily management after start-up

- **Daily OEE review per station** (availability × performance × quality), with the top three losses and an owner for each.
- **Andon response:** red at the checking station means the leader goes to the station within the agreed time. Find the cause; contain the parts made since the last good part.
- **Weekly:** changeover times against the SMED standard; scrap Pareto by defect.
- **Monthly:** fixture check with the master part; recalibration records.

## 5. Risks specific to a transfer

| Risk | Countermeasure |
|---|---|
| Local tube lot has different springback | Re-teach per lot at first; record springback per lot; adjust the model only from measured data |
| Elongation not guaranteed in small tube (JIS) | Elongation stated in the purchase specification; certificate checked at receiving |
| Spare parts lead time (dies, mandrels) | Spares shipped with the line; local supplier qualified within 6 months |
| Language | Bilingual standard work and process sheet (the 工程表 headers are already EN/JP); pictures over text |

## 6. Short version for the A3

Ship the data pack, fixture and standard work. Train the inspection station first. Prove machine repeatability and gauge R&R. Re-teach springback with local material. Ramp from a short run. Review OEE daily.
