"""JIS-designated tube materials, with the source of every value.

Strengths and elongations are the **minimum specified values** in the JIS
table named for each grade (not typical or measured values). Young's modulus
is a typical design value. Every value carries its source URL here and in
docs/ENGINEERING_NOTES.md, section 7.

Two points from the standards matter for bent tube:

* JIS G 3445 (Table 3, note a) and JIS G 3459 (clause 6.1) do not specify
  elongation for tubes of 40 mm OD or less; the test result is only
  recorded. Most two-wheeler tube is that small, so the elongation a bend
  needs has to be written into the purchase specification (dfm.py, rule D8).
* JIS G 3445 specifies no yield point for STKM11A, so any calculation that
  needs one says so instead of assuming a value.

Edition note: the tables were read from JIS G 3445:2016, G 3459:2016 and
H 4080:2015. Later editions exist (G 3445:2021/2025, G 3459:2021,
H 4080:2023) and were not checked; values may differ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

G3445 = "https://kikakurui.com/g3/G3445-2016-01.html (Table 3)"
G3445_NS = "https://www.nipponsteel.com/product/catalog_download/pdf/P011.pdf (Nippon Steel catalog P011, pp. 8-9)"
G3459 = "https://kikakurui.com/g3/G3459-2020-01.html (JIS G 3459:2016, Table 4)"
H4080 = "https://kikakurui.com/h4/H4080-2015-01.html (Table 3, T5, wall <= 12 mm)"
E_STEEL = "https://www.mlit.go.jp/gobuild/content/001517904.pdf (MLIT design standard, Table 4.2.1: 2.05e5 N/mm2)"
E_SUS304 = ("https://d1io3yog0oux5.cloudfront.net/_7ce3a04c09e74bf31ff5f89fc888db25/clevelandcliffs/db/1190/10510/"
            "file/CLF_ProductData_304-304LSS_052021.pdf (Cleveland-Cliffs 304/304L bulletin: 193 GPa)")
E_6063 = "https://www.aerospacemetals.com/wp-content/uploads/2023/06/Aluminum-6063-T5.pdf (68.9 GPa)"


@dataclass(frozen=True)
class Material:
    grade: str
    standard: str
    description: str
    e_mpa: float  #: Young's modulus, MPa (typical design value)
    yield_mpa: float | None  #: minimum yield point or 0.2 % proof stress, MPa; None = not specified
    tensile_mpa: float  #: minimum tensile strength, MPa
    elongation_pct: float  #: minimum elongation after fracture, %, longitudinal test piece
    elongation_unspecified_below_od: float | None = None  #: OD (mm) at or below which elongation is not guaranteed
    sources: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def row(self) -> dict:
        return {
            "grade": self.grade,
            "standard": self.standard,
            "description": self.description,
            "E (GPa)": round(self.e_mpa / 1000.0, 1),
            "yield min (MPa)": self.yield_mpa if self.yield_mpa is not None else "not specified",
            "tensile min (MPa)": self.tensile_mpa,
            "elongation min (%)": self.elongation_pct,
            "note": self.notes,
        }


MATERIALS: dict[str, Material] = {
    "STKM11A": Material(
        grade="STKM11A",
        standard="JIS G 3445",
        description="Carbon steel tube for machine structural purposes",
        e_mpa=205_000.0,
        yield_mpa=None,
        tensile_mpa=290.0,
        elongation_pct=35.0,
        elongation_unspecified_below_od=40.0,
        sources={"tensile, yield, elongation": G3445, "cross-check": G3445_NS, "E": E_STEEL},
        notes="No yield point specified. Elongation not specified for OD <= 40 mm (Table 3 note a).",
    ),
    "STKM13A": Material(
        grade="STKM13A",
        standard="JIS G 3445",
        description="Carbon steel tube for machine structural purposes",
        e_mpa=205_000.0,
        yield_mpa=215.0,
        tensile_mpa=370.0,
        elongation_pct=30.0,
        elongation_unspecified_below_od=40.0,
        sources={"tensile, yield, elongation": G3445, "cross-check": G3445_NS, "E": E_STEEL},
        notes="Elongation not specified for OD <= 40 mm (Table 3 note a).",
    ),
    "SUS304": Material(
        grade="SUS304",
        standard="JIS G 3459 (SUS304TP)",
        description="Austenitic stainless steel pipe",
        e_mpa=193_000.0,
        yield_mpa=205.0,
        tensile_mpa=520.0,
        elongation_pct=35.0,
        elongation_unspecified_below_od=40.0,
        sources={"tensile, 0.2% proof, elongation": G3459, "E": E_SUS304},
        notes="Elongation not applied to OD < 40 mm (clause 6.1); recorded only.",
    ),
    "A6063-T5": Material(
        grade="A6063-T5",
        standard="JIS H 4080",
        description="Aluminium alloy extruded tube, T5 temper",
        e_mpa=68_900.0,
        yield_mpa=110.0,
        tensile_mpa=155.0,
        elongation_pct=8.0,
        sources={"tensile, proof, elongation": H4080, "E": E_6063},
        notes="Wall <= 12 mm. The often-quoted 150 MPa is the extruded-shape standard H 4100, not tube.",
    ),
}


def get(grade: str) -> Material:
    try:
        return MATERIALS[grade]
    except KeyError:
        raise KeyError(f"unknown material {grade!r}; known: {', '.join(MATERIALS)}") from None
