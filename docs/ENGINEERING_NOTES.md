# Engineering notes

This file covers every formula PipeForge uses: where it comes from, what it
assumes, and a worked example. The tests reproduce each example
(`tests/test_geometry.py`, `tests/test_mechanics_dfm_comp.py`). Section
numbers match the references in the code.

Values marked **engineering estimate** come from classical theory or rules
of thumb. They are not measurements or finite-element results.

---

## 1. Centerline geometry (`geometry.py`)

### 1.1 Data conventions

- **XYZ**: the intersection points ("virtual sharps") P0 … Pn. These are where the straights would meet if the bends had no radius. They are the nominal data on a tube drawing.
- **LRA**: for each bend, three values:
  - L, the straight fed before the bend, tangent point to tangent point;
  - R, the plane rotation before the bend;
  - A, the bend angle.
  A final straight closes the list.
- **YBC**: the Eaton Leonard axis naming: Y feed, B rotation, C bend. "LRA is considered the nominal (perfect) data, and YBC is considered to as the adjusted bender data" ([Advanced Tubular](https://advancedtubular.helpjuice.com/vtube-general-step-and-laser/acronyms-for-tube-fabrication)).
  - G. Winton gives the same mapping: "In the YBC data scheme, the Y, B, and C stand for the same attributes" ([The Fabricator, 2008](https://www.thefabricator.com/thefabricator/article/tubepipefabrication/from-the-cad-station-to-the-production-floor)).
  - PipeForge follows that split: LRA describes the part, and YBC is LRA after springback and radius-growth compensation (section 4).

### 1.2 One bend

At an interior point Pi, write u for the unit direction coming in and v for the direction going out.

- Bend angle: θ = arccos(u · v).
- Tangent length: T = CLR · tan(θ/2).
- Tangent points: Pi − u·T and Pi + v·T.
- Arc centre: Pi + CLR / cos(θ/2) along the bisector of (v − u).
- Bend-plane normal: n = (u × v) / |u × v|.
- Arc length: CLR · θ.

Three geometries are rejected outright:
- a collinear point (θ ≈ 0);
- a fold-back (θ → 180°);
- radii whose tangent lengths overlap on a segment.

### 1.3 Plane rotation

R before bend i is the signed angle from n(i−1) to n(i), measured about the feed direction u(i) by the right-hand rule, and wrapped to (−180°, 180°]. The first bend's R is 0 by definition.

The absolute position and orientation are kept separately as a `Placement`: start point, first direction and first normal. With it, XYZ → LRA → XYZ reproduces the points exactly; the tests measure about 1e-13 mm against the brief's 0.01 mm. A bender program carries no placement, so such a bare LRA is compared by rigid (Kabsch) alignment instead.

**Rebuilding XYZ from LRA:**
1. Start at the origin with direction +X and normal +Z.
2. For each bend:
   - rotate the normal about the direction by R;
   - advance T(prev) + L + T to the next intersection point;
   - rotate the direction about the normal by A.

**Hypothesis property test.** 150 random programs go LRA → XYZ → LRA and return the same L, R and A to 1e-6.

### 1.4 Developed (cut) length and elongation

The geometric cut length is ΣL + final straight + Σ CLR·θ.

The arcs stretch during bending: the neutral axis moves towards the inside of the bend.
- "The real straight pipe length is generally shorter than its theoretical length… the difference … is the bending elongation" ([PTC Creo Piping](https://support.ptc.com/help/creo/creo_pma/r9.0/usascii/piping/piping/About_Bending_Elongation.html)).
- Khodayari ties elongation to the neutral-axis displacement × bend angle ([The Fabricator, 2002](https://www.thefabricator.com/tubepipejournal/article/hydroforming/how-material-influences-bending-for-hydroforming)).

No source gives a universal value; E(n) comes from bend tables or trials. `developed_length(..., elongation_pct)` therefore takes the allowance as an input, default 0, and removes that percentage of the arc lengths.

### 1.5 Worked example (test `test_hand_computed_two_bend_case`)

The points are (0,0,0), (100,0,0), (100,100,0) and (100,100,100), with CLR = 20.

- **Bend angles.** Both bends are 90°, so T = 20 · tan 45° = 20 mm.
- **Straights.**
  - First: 100 − 20 = 80.
  - Middle: 100 − 20 − 20 = 60.
  - Last: 100 − 20 = 80.
- **Plane rotation.**
  - Bend 1 turns +X → +Y, so n1 = +Z.
  - Bend 2 turns +Y → +Z, so n2 = +X.
  - About the feed direction +Y, +Z rotates to +X by +90°, so R2 = +90°.
- **Cut length** = 80 + 60 + 80 + 2 · 20 · π/2 = **282.83 mm**.

---

## 2. Springback (`mechanics.py`)

### 2.1 Relation used

Elastic unloading of a bent section obeys "1/R − 1/r = M / (E′I)", where R is the loaded radius and r the unloaded one. This is Wagoner, Wang and Li, "Springback", ASM Handbook, Eq. 4 ([PDF](http://li.mit.edu/Stuff/RHW/Upload/49.pdf)). The source states it for a general cross-section, so it applies to a tube with its own M and I.

For a thin-walled tube with mean radius r_m = (OD − t)/2:
- I = π r_m³ t;
- **fully plastic moment** Mp = 4 r_m² t σ, where σ is the flow stress (thin ring, σ·y integrated around the wall).

### 2.2 Elastic core (exact, elastic–perfectly plastic)

At curvature κ = 1/CLR, fibres closer to the neutral axis than y_e = σ/(Eκ) are still elastic. Define α = arcsin(y_e / r_m). Integrating gives

M = 4 r_m² t σ · [cos α + (α/2 − sin 2α / 4) / sin α].

- As α → 0 the bracket tends to 1, the fully plastic case.
- As α → π/2 it tends to π/4, the elastic moment σI/r_m.

`tests/test_mechanics_dfm_comp.py::test_moment_factor_limits` checks both limits.

### 2.3 Springback angle

The arc keeps its length while it unloads, so the angle falls in proportion to the curvature:

Δθ = θ · CLR · M / (E I), and the radius after unloading = CLR / (1 − Δθ/θ).

### 2.4 Worked example: the TubeBEND tube

Tube 22 × 1 mm, CLR 33 mm, bent to 47°, E = 193 GPa. The flow stress is the SUS304 minimum 0.2% proof stress, 205 MPa.
- r_m = 10.5 mm and y_e = 205 · 33 / 193 000 = 0.035 mm, so the section is 99.8% plastic.
- Δθ ≈ 47 · 4 · 205 · 33 / (π · 193 000 · 10.5) = **0.200°**, with a ratio of 0.00425.

Hardening is not modelled, so `springback_band` reports three flow stresses:

| Flow stress | Springback |
|---|---|
| Yield, 205 MPa | 0.20° |
| Mean of yield and tensile, 362.5 MPa | 0.35° |
| Tensile, 520 MPa | 0.51° |

### 2.5 What the data says

TubeBEND **measured 2.60° ± 0.28°** on this exact tube and tooling (315 runs). Even at the tensile strength, the formula gives 0.51°, about a fifth of the measured value. Pure-bending theory leaves out:
- elastic deflection of the machine and tooling;
- unloading of the pressure die and mandrel;
- clamp slip;
- the work hardening of a cold-drawn stainless tube.

The published shop data agrees with the larger magnitude. Lee & Van Tyne measured 1.46–1.80° at a 90° bend and D = 1.89, and 3.2–5.2° at D = 1.47 ([The Fabricator, 2007](https://www.thefabricator.com/tubepipejournal/article/hydroforming/straining-to-understand-bendingr)). Bend Tooling warns that such rules "are not effective" and that FEA or trials are needed.

**This gap is why shops run trial bends, and why `springback_ml` learns from process data.** The physics estimate stays in the app as an engineering estimate for materials and sizes outside the TubeBEND domain, with this caveat shown next to it.

---

## 3. Wall thickness and ovality (`mechanics.py`)

### 3.1 Extrados thinning and intrados thickening

**Assumptions:** the neutral axis stays on the centerline, volume is constant, and there is no hoop strain. The outer fibre at R + OD/2 then stretches by (R + OD/2)/R, so:

- t_outer = t · R / (R + OD/2), and thinning = 1 / (2R/OD + 1).
  - This matches the Bend Tooling rule of thumb Pt = (Ro − R)/Ro ([formulas](https://bendtooling.com/tube-bending-formulas/)).
  - It also matches Tube Form Solutions' check: "a two-inch tube bent to a three-inch centerline radius will thin by about 25%". At D = 1.5 the formula gives 25.0%.
- t_inner = t · R / (R − OD/2): **our own symmetric derivation, with no published formula found.**
  - At 1D it gives +100%, which is unrealistic, so treat it as an upper bound only.
- **Elongation required** at the extrados: (OD/2)/CLR × 100%. This form is given by Pines, Bend Tooling and Unison.

**Worked example (handlebar):** OD 22.2, t 1.6, CLR 60.
- t_outer = 1.6 · 60 / 71.1 = **1.350 mm**, i.e. 15.6% thinner.
- t_inner = 1.6 · 60 / 48.9 = 1.963 mm (+22.7%, upper bound).
- Elongation needed = 11.1 / 60 = **18.5%**.

### 3.2 Ovality

**Definition:** ovality = (Dmax − Dmin) / Dnominal × 100 ([TFS slides](https://www.slideshare.net/TubeFormSolutions/intro-to-rotary-draw-bending-an-engineers-guide-to-bending-tubes)).

**Acceptance:**
- 5% is Tube Form Solutions' example limit.
- 8% is the UFGS limit for pressure pipe bent at a radius of 5D or more ([UFGS](https://ufgscriteria.tpub.com/4_159_01/4_159_010224.htm)).

Anything else is customer-specific, so PipeForge flags against 5–8%.

**Estimate without a mandrel (TFS):** "Ovality is Estimated at .7 Times Difficulty Factor", with DF = wall factor / D of bend. TFS gives it only for DF under 19 on steel.

| Case | DF | Estimated ovality |
|---|---|---|
| Handlebar | 13.9 / 2.70 = 5.1 | 3.6% |
| TubeBEND tube | 22 / 1.5 = 14.7 | 10.3% |

The TubeBEND runs were bent *with* a mandrel and measured a maximum arc ovality of **2.5–6.6%** (mean 3.96%). This is consistent with a mandrel being required for that tube, which is what the chart in 5.2 says. No closed-form estimate with a mandrel was found, so none is given.

---

## 4. Compensation: LRA → YBC (`compensation.py`)

### 4.1 Overbend

The die must turn through C = A + Δθ so that the bend opens to A when the die releases.

### 4.2 Evaluating springback at the nominal angle

Springback is roughly proportional to the angle (Lee & Van Tyne: "springback increases linearly with target angle"). Evaluating it at C instead of A changes it by a factor C/A ≈ 1 + Δθ/A.
- For the handlebar this is 1.0106, i.e. 0.006°, far below a bender's 0.1° resolution.

### 4.3 Radius growth and feed correction

While the bend opens at constant arc length, its radius grows from CLR to R′ = CLR · C / A. The tangent length grows by g = (R′ − CLR) · tan(A/2). Feeding the nominal L would therefore move every later intersection point outwards.

PipeForge shortens each straight by the growth at both of its ends: Y = L − g(prev) − g(next).

`tests/…::test_compensated_program_reproduces_the_nominal_points` rebuilds the part the machine would make. It reproduces the nominal points to 1e-6 mm, and the same test without the correction misses by more than 1 mm.

**Worked example (handlebar, physics model, STKM13A):**
- Each 55.86° bend springs back 0.591°, so C = **56.448°**.
- R′ = 60.635 mm.
- Y1 = 103.193 − 0.336 = **102.857 mm**.
- Cut length: 907.83 mm (program) against 908.05 mm (nominal).

**ML within its domain.** The TubeBEND model predicts springback at the 47° training angle; `pipeline.py` scales it linearly with angle (above). This is allowed only for the TubeBEND tube and tooling.

**Twist (B correction) is not modelled; B equals R.**

---

## 5. Manufacturability rules (`dfm.py`)

### 5.1 D of bend

"A bend that has a CLR equal to the OD, a 1D bend, is considered an extreme bend; a 2D bend is more manageable, but still severe; and a 3D bend is considered optimal" ([Pines / Canfield, The Fabricator, 2016](https://www.thefabricator.com/tubepipejournal/article/tubepipefabrication/tips-on-designing-tubular-parts-for-bending)).

| D of bend | Result |
|---|---|
| Below 0.6 | fail |
| 0.6–1.0 | warn: "specialist process" |
| 1.0–1.5 | warn: "extreme" |
| 1.5 and above | pass, labelled severe / manageable / optimal |

Yamato publicly reports 0.6DR (CLR = 0.6 × OD) bending as its own technology, so the generic tooling chart is not the limit of what can be made.

### 5.2 Mandrel and wiper die (Bend Tooling Inc. chart)

The full Bend Tooling "Mandrel and Wiper Selection Chart" (© 2011, [PDF](https://bendtooling.com/wp-content/uploads/2017/08/Bend-Tooling-Mandrel-and-Wiper-Selection-Chart-110927.pdf)) is transcribed in `dfm.CHART`: 21 wall-factor rows × 12 D-of-bend columns.

**Reading it** (W. Q. Tingley III, [The Fabricator, 2010](https://www.thefabricator.com/tubepipejournal/article/tubepipefabrication/selecting-the-right-mandrel-and-wiper)): take the largest wall factor (OD/t) not above yours, and the largest D of bend not above yours.

**Shifts:**
- Chart note 4: "For stainless steel, titanium, copper-nickel, and 'T6' aluminum tubing materials, adjust one column to the left."
- Fabricator article: one column right if the bend is under 45°.

**Codes:** 1st character N/R/C/D = no mandrel / regular / close / double-close pitch; 2nd 0 = plug, 1–9 = number of balls; 3rd N/W/H = no wiper / inserted mandrel + wiper / high-pressure tooling.

**Check:** Tube Form Solutions' example, "2.00 OD, .065 Wall, 4.0″ CLR, Stainless … Requires 2 Ball Mandrel a Wiper Die", reproduces as R2W in `test_chart_lookup_and_shifts`.

### 5.3 Straights and clamping

- **Clamp length.** Bend Tooling gives Lc = OD·(Kr·2.5) − R, not less than OD·Ks. With Kr = 2 this is **5·OD − CLR, not less than 2·OD** (smooth clamp) or 1·OD (serrated).
- **Minimum distance between bends** (Pines): "If the D of bend is > 2, the minimum DBB is 3 x OD. If the D of bend is ≤ 2, the minimum DBB is 4 x OD."
- **Rule D3** uses the larger of the two:

| Straight vs requirement | Result |
|---|---|
| Meets it | pass |
| At least half of it | warn: short or serrated clamp, or clamp-in-bend tooling |
| Less than half | fail |

### 5.4 Tube ends

L. McGrew ([The Fabricator, 2008](https://www.thefabricator.com/thefabricator/article/tubepipefabrication/waste-not-want-not---reducing-scrap-in-bending-tube-pipe)):
- "the first straight must be at least 1.5D … If boost is not used, the first straight should be at least 2D." Otherwise add clamping stock = 2·OD − SL1 and trim it after bending.
- "It is commonly accepted that the collet depth minimum is 0.5D."

### 5.5 Collision while bending

The bend sequence is simulated in the machine frame:
- the bend die tangent point is at the origin;
- the unbent stock lies along −X;
- each bend turns towards +Y about +Z.

At each 15° step of every bend, the swinging leading part, carrying the bends already formed, is checked against three regions:
- the floor (tube axis height);
- the machine bed behind the die;
- the bend-head box.

The arc being formed wraps the bend die and is excluded. Both bending directions are tried. If only the reverse is clear, the rule recommends bending from the tube end; if neither is clear, a left/right-hand machine or splitting the part.

The machine envelope is **illustrative**; replace it with the real machine's data sheet.

### 5.6 Elongation versus the material standard (rule D8)

The elongation the bend needs (3.1) is compared with the minimum in the JIS table (section 7). **JIS G 3445 (Table 3, note a) and JIS G 3459 (clause 6.1) do not specify elongation for tubes of 40 mm OD or less**; it is only recorded. Most two-wheeler and four-wheeler tube is that small, so the rule warns that the required elongation belongs in the purchase specification.

Example: the A6063-T5 coolant pipe needs 20.0% against a JIS H 4080 minimum of 8%, so **it fails**. The rule suggests bending in a softer temper (O or T4, ageing afterwards) or raising the CLR to at least 100 mm. This is a real finding about my own sample part.

### 5.7 Self-interference

Two sections of the tube that are far apart along it must not come closer than OD, centre to centre.

---

## 6. Production metrics (`line_sim.py`, `kaizen.py`)

### 6.1 Takt time

Takt = available production time / customer demand ([Lean Enterprise Institute](https://www.lean.org/lexicon-terms/takt-time/)).

Baseline: 2 shifts × (480 − 60) min = 50 400 s per day, at a demand of 1 500 parts/day, gives **33.6 s**.

### 6.2 OEE

OEE = availability × performance × quality ([oee.com](https://www.oee.com/calculating-oee/)), which equals good count × ideal cycle time / planned time.
- **Availability** loses breakdowns and changeovers.
- **Performance** loses slow cycles, plus starved and blocked time.
- **Quality** loses scrap.

`test_oee_is_availability_times_performance_times_quality` checks the identity on simulated data.

### 6.3 Yamazumi

The work content of each station is stacked by element (manual, machine or walk) against the takt line ([LEI: operator balance chart](https://www.lean.org/lexicon-terms/operator-balance-chart/)).

### 6.4 SMED

Single-minute exchange of die: separate internal steps (machine stopped) from external ones, convert internal to external, then shorten what stays internal ([LEI](https://www.lean.org/lexicon-terms/single-minute-exchange-of-die/)). The bender changeover study is in `kaizen.SMED_STEPS`, with synthetic times.

### 6.5 Simulation model

**All line parameters are synthetic and illustrative:** cycle times, MTBF/MTTR, changeovers and yields.

- **Cycle times** are lognormal.
- **Failures** arrive while running (exponential).
- **Bend defects are latent:** they are found only at the checking fixture, after they have used TIG-weld capacity.
- **Runs:** 10 replications × 5 days, with common random numbers across scenarios.
- **Real-data input:** the bending yield in the springback scenario comes from M3 on real TubeBEND runs. It is applied to the part as if it had one critical bend. A part with n independent bends would see yield^n, so this mapping understates the gain on purpose.

---

## 7. Materials (`materials.py`)

All strengths are **minimum specified values** from the JIS table named. Edition caveat: the tables were read from G 3445:2016, G 3459:2016 and H 4080:2015; later editions were not checked.

### 7.1 STKM11A and STKM13A, JIS G 3445 Table 3

Source: [kikakurui](https://kikakurui.com/g3/G3445-2016-01.html); cross-checked against [Nippon Steel catalog P011](https://www.nipponsteel.com/product/catalog_download/pdf/P011.pdf).

| Grade | Tensile | Yield | Elongation (No.11/12, longitudinal) |
|---|---|---|---|
| STKM11A | ≥ 290 MPa | **not specified** | ≥ 35% |
| STKM13A | ≥ 370 MPa | ≥ 215 MPa | ≥ 30% |

Note a): elongation is not specified for OD ≤ 40 mm.

### 7.2 SUS304TP, JIS G 3459 Table 4

Source: [kikakurui](https://kikakurui.com/g3/G3459-2020-01.html).

Tensile ≥ 520 MPa, 0.2% proof ≥ 205 MPa, elongation ≥ 35%. Clause 6.1: elongation is not applied to OD < 40 mm.

### 7.3 A6063-T5 extruded tube, JIS H 4080 Table 3 (wall ≤ 12 mm)

Source: [kikakurui](https://kikakurui.com/h4/H4080-2015-01.html).

Tensile ≥ 155 MPa, proof ≥ 110 MPa, elongation ≥ 8%. The often-quoted 150 MPa is the extruded-shape standard H 4100, not the tube standard.

### 7.4 What is not used

STKM11A has no specified yield, so PipeForge gives no physics springback for it: the app asks for a springback measured on trial bends.

### 7.5 Young's modulus (typical design values)

| Material | E | Source |
|---|---|---|
| Carbon steel | 205 GPa | [MLIT design standard, Table 4.2.1](https://www.mlit.go.jp/gobuild/content/001517904.pdf) |
| SUS304 | 193 GPa | [Cleveland-Cliffs 304/304L bulletin](https://d1io3yog0oux5.cloudfront.net/_7ce3a04c09e74bf31ff5f89fc888db25/clevelandcliffs/db/1190/10510/file/CLF_ProductData_304-304LSS_052021.pdf) |
| 6063-T5 | 68.9 GPa | [Aerospace Metals datasheet](https://www.aerospacemetals.com/wp-content/uploads/2023/06/Aluminum-6063-T5.pdf) |

---

## 8. Not built (cut, per the brief's cut order)

- **M5 control-cable calculator.** The capstan relation T₂ = T₁·e^(μθ) was researched. Cablecraft's efficiency factors imply μ of about 0.05 for a PTFE-covered core and 0.09–0.10 uncovered, but these are derived, not measured, values. The module was cut for time.
- **M8 vision.**

Neither appears in any claim.
