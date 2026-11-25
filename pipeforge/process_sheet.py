"""工程表 / control plan for a bent-tube part, as Excel (openpyxl) and PDF (reportlab).

Every value in the sheet is copied from :class:`pipeforge.pipeline.Analysis`
(cut length, YBC program, tooling, DFM findings, fixture and sensors). The
operation list and the reaction plans are the generic structure of a tube
cell, written for this study; parameters that the study does not compute
(TIG welding current, gas flow) point to the welding procedure (WPS) instead
of inventing numbers. Headers are English with Japanese (工程, 設備, 管理項目,
検査方法, 頻度, 異常処置); the Japanese was written while learning and was
not checked by a native speaker.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .pipeline import Analysis

HEADERS = [
    ("No.", "工程No"),
    ("Operation", "工程名"),
    ("Machine", "設備"),
    ("Control item", "管理項目"),
    ("Specification", "規格"),
    ("Inspection method", "検査方法"),
    ("Frequency", "頻度"),
    ("Record", "記録"),
    ("Reaction plan", "異常処置"),
]


def operations(a: Analysis) -> list[list[str]]:
    p = a.part
    y = a.ybc
    tool = a.dfm.tooling.get("class", "per chart")
    fx = a.fixture
    n_clamp = sum(b.clamp for b in fx.blocks)
    bend_spec = "; ".join(f"B{r.bend}: C {r.C:.2f} deg (A {r.nominal_A:.2f} + {r.springback:.2f})" for r in y.rows)
    return [
        ["10", "Cut to length / 切断", "Cut-off saw", "Blank length",
         f"{y.cut_length:.1f} mm +/-1.0 (example tolerance)", "Length stop gauge, tape",
         "First piece, then 1 per 50", "Check sheet", "Stop; reset the stop; check parts since the last good check"],
        ["20", "End forming / 端末加工", "End forming press", "End form per drawing (flare / bead)",
         "Per drawing (not defined in this study)", "Go/no-go gauge", "First piece, then 1 per hour",
         "Check sheet", "Stop; check the die; quarantine the batch"],
        ["30", "Bending / 曲げ", "CNC rotary-draw bender",
         f"YBC program, {p.n_bends} bends, CLR {', '.join(f'{r:g}' for r in sorted(set(p.radii)))} mm",
         bend_spec, f"Checking fixture (op 50); tooling: {tool}", "First piece after every changeover",
         "Program revision, first-article record",
         f"Re-teach springback ({a.springback_model}); stop if two parts fail in a row"],
        ["30a", "Bending / 曲げ", "CNC rotary-draw bender", "Bend angles", "+/-0.5 deg (example tolerance)",
         "Checking fixture", "100 %", "Station log", "Andon; NG bin; review springback offset"],
        ["30b", "Bending / 曲げ", "CNC rotary-draw bender", "Wall thinning (estimate)",
         f"max {max((b['thinning_pct'] or 0) for b in a.bends):.1f}% at the extrados (engineering estimate)",
         "Sectioning, first article only", "Per new material lot", "Lab report",
         "Hold the lot; check material elongation certificate"],
        ["40", "TIG welding / TIG溶接", "TIG welding cell with jig", "Bracket position and weld",
         "Per drawing and WPS (not defined in this study)", "Visual + position gauge", "100 % visual, 1 per hour gauge",
         "Check sheet", "Stop; check jig and WPS; quarantine"],
        ["50", "Inspection / 検査", f"Checking fixture {p.part_no}-F ({len(fx.blocks)} blocks, {n_clamp} clamps)",
         "Tube seated in all grooves; both ends at stops",
         f"groove clearance {fx.clearance} mm; all {len(fx.sensors())} sensors ON",
         "Automated station (PLC sequence, poka-yoke)", "100 %", "PASS label, station log",
         "Red andon; part to NG bin (sensor-confirmed)"],
        ["60", "Packing / 梱包", "Packing table", "Quantity and label", "Per packing standard",
         "Count, label scan", "Every box", "Shipping record", "Re-count; correct the label"],
    ]


def header_info(a: Analysis) -> list[tuple[str, str]]:
    p = a.part
    return [
        ("Part no. / 品番", p.part_no),
        ("Part name / 品名", f"{p.name} / {p.name_ja}" if p.name_ja else p.name),
        ("Material / 材質", p.material),
        ("Tube / 寸法", f"OD {p.od:g} x t {p.wall:g} mm"),
        ("Cut length / 切断長", f"{a.ybc.cut_length:.1f} mm (program), {a.cut_length_nominal:.1f} mm (nominal)"),
        ("Springback model", a.springback_note),
        ("Bend sequence", a.dfm.sequence),
        ("Date / 作成日", _dt.date.today().isoformat()),
        ("Prepared by / 作成", "PipeForge (generated); study document, not a released control plan"),
    ]


def write_excel(a: Analysis, path: str | Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "工程表 Control plan"
    thin = Side(style="thin", color="555555")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="16181B")
    key_fill = PatternFill("solid", fgColor="EEF1F4")
    jp = "Meiryo"
    ws["A1"] = "工程表 / Process control plan"
    ws["A1"].font = Font(name=jp, size=14, bold=True)
    r = 3
    for k, v in header_info(a):
        ws.cell(r, 1, k).font = Font(name=jp, bold=True)
        ws.cell(r, 1).fill = key_fill
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=9)
        ws.cell(r, 2, v).font = Font(name=jp)
        r += 1
    r += 1
    for c, (en, ja) in enumerate(HEADERS, start=1):
        cell = ws.cell(r, c, f"{ja}\n{en}")
        cell.font = Font(name=jp, bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = box
    ws.row_dimensions[r].height = 32
    for row in operations(a):
        r += 1
        for c, v in enumerate(row, start=1):
            cell = ws.cell(r, c, v)
            cell.font = Font(name=jp, size=9)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = box
    for c, w in enumerate((7, 18, 22, 24, 34, 24, 18, 16, 30), start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.freeze_panes = ws.cell(r - len(operations(a)), 1)

    def table(title: str, rows: list[dict]) -> None:
        sh = wb.create_sheet(title)
        if not rows:
            sh["A1"] = "none"
            return
        keys = list(rows[0].keys())
        for c, k in enumerate(keys, start=1):
            cell = sh.cell(1, c, k)
            cell.font = Font(name=jp, bold=True, color="FFFFFF")
            cell.fill = head_fill
            sh.column_dimensions[get_column_letter(c)].width = max(10, min(60, len(k) + 4))
        for i, row in enumerate(rows, start=2):
            for c, k in enumerate(keys, start=1):
                v = row[k]
                sh.cell(i, c, v if isinstance(v, (int, float, str)) or v is None else str(v)).font = Font(name=jp)

    table("曲げ YBC program", [{**r, "radius after springback": round(rr.radius_after, 3)}
                                for r, rr in zip(a.ybc.as_table(), a.ybc.rows, strict=True)])
    table("LRA nominal", a.lra)
    table("Bends (estimates)", [{k: (str(v) if isinstance(v, list) else v) for k, v in b.items()} for b in a.bends])
    table("DFM", a.dfm.as_rows())
    table("治具 Fixture", a.fixture.block_table())
    table("I-O list", a.io)
    notes = wb.create_sheet("Notes")
    for i, line in enumerate((
        "Study document generated by PipeForge. Not a released control plan.",
        "Tolerances marked 'example' are illustrative, not from a customer drawing.",
        "Wall thinning and physics springback are engineering estimates (docs/ENGINEERING_NOTES.md).",
        "The ML springback model is valid only for the TubeBEND tube and tooling.",
        "Japanese headers were written while learning; not reviewed by a native speaker.",
    ), start=1):
        notes.cell(i, 1, line)
    wb.save(path)
    return path


def write_pdf(a: Analysis, path: str | Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(path)
    font = "HeiseiKakuGo-W5"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    body = ParagraphStyle("b", fontName=font, fontSize=7.5, leading=9.5)
    title = ParagraphStyle("t", fontName=font, fontSize=14, leading=18)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A3), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=f"{a.part.part_no} control plan")
    flow = [Paragraph("工程表 / Process control plan", title), Spacer(1, 4 * mm)]
    info = Table([[Paragraph(k, body), Paragraph(v, body)] for k, v in header_info(a)], colWidths=[55 * mm, 330 * mm])
    info.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                              ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF1F4"))]))
    flow += [info, Spacer(1, 5 * mm)]
    head = [Paragraph(f"{ja}<br/>{en}", ParagraphStyle("h", parent=body, textColor=colors.white)) for en, ja in HEADERS]
    rows = [head] + [[Paragraph(str(v), body) for v in row] for row in operations(a)]
    widths = [12, 30, 40, 45, 70, 45, 35, 30, 60]
    t = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16181B")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    flow += [t, Spacer(1, 5 * mm)]
    ybc = [["Bend", "Y (mm)", "B (deg)", "C (deg)", "springback (deg)", "L nominal", "A nominal"]]
    ybc += [[str(r["bend"]), f"{r['Y']:.2f}", f"{r['B']:.2f}", f"{r['C']:.2f}", f"{r['springback']:.3f}",
             f"{r['L nominal']:.2f}", f"{r['A nominal']:.2f}"] for r in a.ybc.as_table()]
    t2 = Table([[Paragraph(c, body) for c in row] for row in ybc])
    t2.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF1F4"))]))
    flow += [Paragraph("曲げプログラム / Bending program (YBC, springback-compensated)", body), Spacer(1, 2 * mm), t2,
             Spacer(1, 4 * mm),
             Paragraph("Study document generated by PipeForge; not a released control plan. Example tolerances are "
                       "illustrative. Thinning and physics springback are engineering estimates.", body)]
    doc.build(flow)
    return path
