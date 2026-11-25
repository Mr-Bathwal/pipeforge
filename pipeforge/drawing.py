"""A3 landscape engineering drawing of a bent tube, as PDF and SVG.

Contents: front, top and right views in third-angle projection, plus an
isometric view that is not to scale. The sheet also carries:

* overall dimensions, and a bend table (intersection-point XYZ and LRA);
* a cut-length note, and general tolerances labelled as examples;
* a revision table, and a title block with the third-angle symbol.

Outlines are true silhouettes: the tube mesh is projected onto each view
plane and the triangles are merged (shapely), so a bend seen edge-on is
drawn correctly rather than as an offset of the projected centerline.
Everything is in millimetres on the sheet; dimension values are full size.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402
from shapely.geometry import Polygon as SPoly  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from .geometry import Vec, bounding_box, centerline, developed_length, xyz_to_lra  # noqa: E402
from .mesh import tube_mesh  # noqa: E402

SHEET_W, SHEET_H = 420.0, 297.0  # A3 landscape, mm
MARGIN = 10.0
STANDARD_SCALES = (1.0, 0.5, 0.4, 0.2, 0.1, 0.05)  # 1:1, 1:2, 1:2.5, 1:5, 1:10, 1:20
LINE = "#111111"
THIN, MEDIUM, THICK = 0.25, 0.45, 0.7

# view name -> (horizontal axis index, sign), (vertical axis index, sign)
# Third angle: front looks along +Y (X right, Z up); top is above it (X right, Y up);
# right is to its right (Y right, Z up).
VIEWS = {
    "FRONT": ((0, 1), (2, 1)),
    "TOP": ((0, 1), (1, 1)),
    "RIGHT": ((1, 1), (2, 1)),
}


@dataclass
class DrawingInfo:
    part_no: str
    name: str
    material: str
    od: float
    wall: float
    drawn_by: str = "PipeForge (generated)"
    date: str = field(default_factory=lambda: _dt.date.today().isoformat())
    revision: str = "A"
    revision_note: str = "Initial issue, generated from XYZ data"


def _project(pts: Vec, view: str) -> Vec:
    (h, hs), (v, vs) = VIEWS[view]
    return np.column_stack([pts[:, h] * hs, pts[:, v] * vs])


def _silhouette(p2: Vec, faces: np.ndarray):  # type: ignore[no-untyped-def]
    """Union of the projected triangles: the exact outline of the projected mesh."""
    t = p2[faces]
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    return unary_union([SPoly(tri) for tri in t[area > 1e-6]]).buffer(0)


def _iso(pts: Vec) -> Vec:
    """Isometric projection, viewed from (+1, +1, +1): X and Y axes at 30 deg."""
    c30, s30 = np.cos(np.radians(30.0)), 0.5
    return np.column_stack([(pts[:, 0] - pts[:, 1]) * c30, pts[:, 2] - (pts[:, 0] + pts[:, 1]) * s30])


def choose_scale(extents: dict[str, tuple[float, float]], box_w: float, box_h: float) -> float:
    """Largest standard scale at which the three views fit the view area."""
    fx, _ = extents["FRONT"]
    _, ty = extents["TOP"]
    rx, fz = extents["RIGHT"]
    gap = 26.0  # room for dimensions between and around views
    for s in STANDARD_SCALES:
        if (fx + rx) * s + 2 * gap <= box_w and (ty + fz) * s + 2 * gap <= box_h:
            return s
    return STANDARD_SCALES[-1]


def scale_label(s: float) -> str:
    return "1:1" if s == 1.0 else f"1:{1 / s:g}"


def _dim_h(ax, x0: float, x1: float, y: float, y_from: float, value: float) -> None:  # type: ignore[no-untyped-def]
    for x in (x0, x1):
        ax.plot([x, x], [y_from, y - 1.5 * np.sign(y - y_from)], color=LINE, lw=THIN)
    ax.annotate("", xy=(x0, y), xytext=(x1, y), arrowprops=dict(arrowstyle="<|-|>", lw=THIN, color=LINE, shrinkA=0, shrinkB=0, mutation_scale=6))
    ax.text((x0 + x1) / 2, y + 1.0, f"{value:.1f}", ha="center", va="bottom", fontsize=6.5)


def _dim_v(ax, y0: float, y1: float, x: float, x_from: float, value: float) -> None:  # type: ignore[no-untyped-def]
    for y in (y0, y1):
        ax.plot([x_from, x - 1.5 * np.sign(x - x_from)], [y, y], color=LINE, lw=THIN)
    ax.annotate("", xy=(x, y0), xytext=(x, y1), arrowprops=dict(arrowstyle="<|-|>", lw=THIN, color=LINE, shrinkA=0, shrinkB=0, mutation_scale=6))
    ax.text(x - 1.0, (y0 + y1) / 2, f"{value:.1f}", ha="right", va="center", fontsize=6.5, rotation=90)


def _draw_shape(ax, geom, tx, lw: float = MEDIUM, fill: str | None = "#eef1f4") -> None:  # type: ignore[no-untyped-def]
    polys = getattr(geom, "geoms", [geom])
    for poly in polys:
        if poly.is_empty:
            continue
        ext = tx(np.asarray(poly.exterior.coords))
        if fill:
            ax.add_patch(Polygon(ext, closed=True, facecolor=fill, edgecolor="none", zorder=1))
        ax.plot(ext[:, 0], ext[:, 1], color=LINE, lw=lw, zorder=3)
        for ring in poly.interiors:
            r = tx(np.asarray(ring.coords))
            ax.add_patch(Polygon(r, closed=True, facecolor="white", edgecolor="none", zorder=2))
            ax.plot(r[:, 0], r[:, 1], color=LINE, lw=lw, zorder=3)


def _third_angle_symbol(ax, x: float, y: float, s: float = 1.0) -> None:  # type: ignore[no-untyped-def]
    """ISO third-angle symbol: truncated cone, end view to its right."""
    big, small, length = 5.0 * s, 2.8 * s, 7.0 * s
    ax.add_patch(Polygon([[x, y - big], [x + length, y - small], [x + length, y + small], [x, y + big]],
                         closed=True, fill=False, lw=THIN, color=LINE))
    cx = x + length + 4.0 * s + big
    ax.add_patch(Circle((cx, y), big, fill=False, lw=THIN, color=LINE))
    ax.add_patch(Circle((cx, y), small, fill=False, lw=THIN, color=LINE))
    ax.plot([x - 1.5 * s, cx + big + 1.5 * s], [y, y], color=LINE, lw=THIN * 0.8, ls=(0, (8, 2, 1, 2)))


def make_drawing(points, clr, info: DrawingInfo, pdf_path: str | Path | None = None,  # type: ignore[no-untyped-def]
                 svg_path: str | Path | None = None) -> dict:
    """Render the sheet; returns the scale used and the table rows drawn."""
    pts = np.asarray(points, dtype=float)
    lra = xyz_to_lra(pts, clr)
    cut = developed_length(lra)
    mesh = tube_mesh(pts, clr, info.od, info.wall, segments=24, step_deg=6.0)
    cl = centerline(pts, clr, step_deg=3.0)
    lo, hi = bounding_box(pts, clr, info.od)
    size = hi - lo

    fig = plt.figure(figsize=(SHEET_W / 25.4, SHEET_H / 25.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, SHEET_W)
    ax.set_ylim(0, SHEET_H)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((MARGIN, MARGIN), SHEET_W - 2 * MARGIN, SHEET_H - 2 * MARGIN, fill=False, lw=THICK, color=LINE))

    # ---- view layout (left area), top view above front, right view to its right
    area_x0, area_y0, area_w, area_h = MARGIN + 4, MARGIN + 56, 258.0, SHEET_H - 2 * MARGIN - 62
    extents = {v: (float(size[VIEWS[v][0][0]]), float(size[VIEWS[v][1][0]])) for v in VIEWS}
    s = choose_scale(extents, area_w, area_h)
    fx, fz = extents["FRONT"]
    _, ty = extents["TOP"]
    ry, _ = extents["RIGHT"]
    gap = 24.0
    used_w = (fx + ry) * s + gap
    used_h = (ty + fz) * s + gap
    x_front = area_x0 + max(12.0, (area_w - used_w) / 2)
    y_front = area_y0 + max(12.0, (area_h - used_h) / 2)
    origins = {
        "FRONT": (x_front, y_front),
        "TOP": (x_front, y_front + fz * s + gap),
        "RIGHT": (x_front + fx * s + gap, y_front),
    }
    for view, (ox, oy) in origins.items():
        (h, _), (v, _) = VIEWS[view]
        lo2 = np.array([lo[h], lo[v]])

        def tx(p2, ox=ox, oy=oy, lo2=lo2):  # noqa: B008
            return (p2 - lo2) * s + np.array([ox, oy])

        sil = _silhouette(_project(mesh.vertices, view), mesh.faces)
        _draw_shape(ax, sil, tx)
        c2 = tx(_project(cl, view))
        ax.plot(c2[:, 0], c2[:, 1], color=LINE, lw=THIN, ls=(0, (10, 2, 1.5, 2)), zorder=4)
        ip = tx(_project(pts, view))
        ax.plot(ip[:, 0], ip[:, 1], color="#8a95a3", lw=THIN * 0.8, ls=":", zorder=4)
        for k, q in enumerate(ip):
            ax.text(q[0] + 1.2, q[1] + 1.2, f"P{k}", fontsize=4.8, color="#334", zorder=5)
        w, hgt = extents[view][0] * s, extents[view][1] * s
        _dim_h(ax, ox, ox + w, oy - 7, oy, extents[view][0])
        _dim_v(ax, oy, oy + hgt, ox - 7, ox, extents[view][1])
        ax.text(ox + w / 2, oy + hgt + 3, f"{view} VIEW", ha="center", va="bottom", fontsize=7, weight="bold")

    # ---- isometric, not to scale, bottom of the view area
    iso_sil = _silhouette(_iso(mesh.vertices), mesh.faces)
    ib = np.array(iso_sil.bounds)
    iso_w, iso_h = 150.0, 38.0
    k = min(iso_w / max(ib[2] - ib[0], 1e-9), iso_h / max(ib[3] - ib[1], 1e-9))
    iso_org = np.array([MARGIN + 12, MARGIN + 6])

    def itx(p2):  # type: ignore[no-untyped-def]
        return (p2 - ib[:2]) * k + iso_org

    _draw_shape(ax, iso_sil, itx, lw=THIN + 0.1, fill="#dfe5ec")
    ax.text(iso_org[0], iso_org[1] + iso_h + 2, "ISOMETRIC (NOT TO SCALE)", fontsize=6, weight="bold")

    # ---- bend table (right column, top)
    tbl_x, tbl_top = 282.0, SHEET_H - MARGIN - 4
    cols = ["PT", "X", "Y", "Z", "L", "R", "A", "CLR"]
    widths = [10, 17, 17, 17, 16, 15, 15, 13]
    rows = []
    lra_rows = list(lra.rows)
    for i, p in enumerate(pts):
        if i == 0:
            rows.append([f"P{i}", *(f"{c:.2f}" for c in p), "", "", "", ""])
        elif i < len(pts) - 1:
            r = lra_rows[i - 1]
            rows.append([f"P{i}", *(f"{c:.2f}" for c in p), f"{r.L:.2f}", f"{r.R:.2f}", f"{r.A:.2f}", f"{r.clr:.1f}"])
        else:
            rows.append([f"P{i}", *(f"{c:.2f}" for c in p), f"{lra.final_L:.2f}", "", "", ""])
    rh = 4.6
    ax.text(tbl_x, tbl_top, "BEND TABLE (intersection points, nominal LRA)", fontsize=6.5, weight="bold", va="top")
    y = tbl_top - 6
    for r_i, row in enumerate([cols, *rows]):
        x = tbl_x
        for c, wdt in zip(row, widths, strict=True):
            ax.add_patch(Rectangle((x, y - rh), wdt, rh, fill=r_i == 0, facecolor="#e9edf2", lw=THIN, edgecolor=LINE))
            ax.text(x + wdt / 2, y - rh / 2, c, fontsize=5.4, ha="center", va="center", weight="bold" if r_i == 0 else None)
            x += wdt
        y -= rh
    notes = [
        f"CUT LENGTH (developed, geometric): {cut:.1f} mm",
        "L = straight before bend (tangent to tangent), R = plane rotation (deg),",
        "A = bend angle (deg), CLR = centerline radius. Nominal values, no springback.",
        "",
        "GENERAL TOLERANCES (EXAMPLE VALUES FOR THIS STUDY, NOT A CUSTOMER SPEC):",
        "  straights +/-0.5 mm   bend angles +/-0.5 deg   rotations +/-0.5 deg",
        "  cut length +/-1.0 mm  tube ends checked on fixture end pins",
        "  ovality at bends <= 8 % of OD (flag; see ENGINEERING_NOTES 3.2)",
        "",
        "Dimensions in mm. Third-angle projection. Do not scale drawing.",
        "Synthetic part for a self-directed study, not a production drawing.",
    ]
    for line in notes:
        y -= 4.2
        ax.text(tbl_x, y, line, fontsize=5.6, va="top")

    # ---- revision table (above the title block)
    rv_y = MARGIN + 64
    ax.add_patch(Rectangle((tbl_x, rv_y), 128, 10, fill=False, lw=THIN, color=LINE))
    ax.plot([tbl_x + 12, tbl_x + 12], [rv_y, rv_y + 10], color=LINE, lw=THIN)
    ax.plot([tbl_x + 104, tbl_x + 104], [rv_y, rv_y + 10], color=LINE, lw=THIN)
    ax.plot([tbl_x, tbl_x + 128], [rv_y + 5, rv_y + 5], color=LINE, lw=THIN)
    for txt, x in (("REV", tbl_x + 6), ("DESCRIPTION", tbl_x + 58), ("DATE", tbl_x + 116)):
        ax.text(x, rv_y + 7.5, txt, fontsize=5, ha="center", va="center", weight="bold")
    for txt, x in ((info.revision, tbl_x + 6), (info.revision_note, tbl_x + 58), (info.date, tbl_x + 116)):
        ax.text(x, rv_y + 2.5, txt, fontsize=5, ha="center", va="center")

    # ---- title block (bottom right)
    tb_x, tb_y, tb_w, tb_h = tbl_x, MARGIN, 128.0, 52.0
    ax.add_patch(Rectangle((tb_x, tb_y), tb_w, tb_h, fill=False, lw=THICK, color=LINE))
    fields = [
        ("PART NO.", info.part_no), ("PART NAME", info.name),
        ("MATERIAL", info.material), ("TUBE", f"OD {info.od:g} x t {info.wall:g} mm"),
        ("CUT LENGTH", f"{cut:.1f} mm"), ("SCALE", f"{scale_label(s)}  (A3)"),
        ("DRAWN", info.drawn_by), ("DATE / REV", f"{info.date} / {info.revision}"),
    ]
    rh2 = tb_h / 4
    for i, (k_, v_) in enumerate(fields):
        col, row = i % 2, i // 2
        x0 = tb_x + col * tb_w / 2
        y0 = tb_y + tb_h - (row + 1) * rh2
        ax.add_patch(Rectangle((x0, y0), tb_w / 2, rh2, fill=False, lw=THIN, color=LINE))
        ax.text(x0 + 1.2, y0 + rh2 - 1.2, k_, fontsize=4.2, va="top", color="#445")
        ax.text(x0 + 1.2, y0 + 2.0, v_, fontsize=6.2 if len(v_) < 30 else 5.0, va="bottom", weight="bold")
    _third_angle_symbol(ax, tb_x - 32, tb_y + 8, s=0.9)
    ax.text(tb_x - 32, tb_y + 15.5, "THIRD ANGLE", fontsize=4.5)
    ax.text(MARGIN + 3, SHEET_H - MARGIN - 4, "PipeForge study drawing", fontsize=6, va="top", color="#556")

    out = {"scale": scale_label(s), "cut_length": cut, "rows": rows}
    for path in (pdf_path, svg_path):
        if path is not None:
            fig.savefig(str(path), format=Path(path).suffix.lstrip("."), metadata={"Creator": "PipeForge"})
    plt.close(fig)
    return out
