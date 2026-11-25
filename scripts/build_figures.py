"""Regenerate every figure used in the README into docs/figures/.

Inputs are the sample parts and the committed artifacts (springback metrics,
kaizen results), so the figures always match the numbers in the repository.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeforge.drawing import DrawingInfo, make_drawing  # noqa: E402
from pipeforge.fixture import design_fixture  # noqa: E402
from pipeforge.line_sim import baseline_line, yamazumi  # noqa: E402
from pipeforge.mesh import tube_mesh  # noqa: E402
from pipeforge.parts import sample_parts  # noqa: E402

OUT = ROOT / "docs" / "figures"
INK, ORANGE, STEEL, MUTED, PAPER = "#16181B", "#E8501A", "#9AA3AD", "#5B6068", "#F4F2EE"


def _view(azim: float = -55.0, elev: float = 28.0) -> np.ndarray:
    """Rotation taking world coordinates to (screen x, screen y, depth towards the viewer)."""
    az, el = np.radians(azim), np.radians(elev)
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(el - np.pi / 2), -np.sin(el - np.pi / 2)],
                   [0, np.sin(el - np.pi / 2), np.cos(el - np.pi / 2)]])
    return rx @ rz


def _render(ax, groups: list[tuple[np.ndarray, str, float]], rot: np.ndarray,  # type: ignore[no-untyped-def]
            base: tuple[np.ndarray, str] | None = None) -> None:
    """Painter's algorithm: every triangle sorted by depth, filled with Lambert shading.

    *base* (the fixture plate) is drawn first and unsorted: everything sits on top of it and the view
    is from above, so it never hides anything, while its two huge triangles would defeat a depth sort.
    """
    from matplotlib.collections import PolyCollection

    tris_all, cols_all, depth_all = [], [], []
    if base is not None:
        nz_all = np.cross(base[0][:, 1] - base[0][:, 0], base[0][:, 2] - base[0][:, 0])[:, 2]
        base = (base[0][nz_all > -1e-9], base[1])  # the underside is never visible from above
        bt = base[0] @ rot.T
        rgb = np.array(matplotlib.colors.to_rgb(base[1]))
        nz = np.cross(base[0][:, 1] - base[0][:, 0], base[0][:, 2] - base[0][:, 0])[:, 2]
        shade = [tuple(rgb * (1.0 if z > 1e-9 else 0.62)) for z in nz]
        order = np.argsort(bt[:, :, 2].mean(axis=1))
        ax.add_collection(PolyCollection(bt[order][:, :, :2], facecolors=np.array(shade)[order], edgecolors="none"))
    light = rot.T @ np.array([0.35, 0.55, 0.75])
    light /= np.linalg.norm(light)
    for tris, color, _edge in groups:
        rgb = np.array(matplotlib.colors.to_rgb(color))
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        k = 0.50 + 0.50 * np.abs(n @ light)
        scr = tris @ rot.T
        tris_all.append(scr[:, :, :2])
        cols_all.append(np.clip(rgb[None, :] * k[:, None] + 0.04, 0, 1))
        depth_all.append(scr[:, :, 2].mean(axis=1))
    tris2 = np.concatenate(tris_all)
    cols = np.concatenate(cols_all)
    tris2_all = np.concatenate([tris2, (base[0] @ rot.T)[:, :, :2]]) if base is not None else tris2
    order = np.argsort(np.concatenate(depth_all))
    ax.add_collection(PolyCollection(tris2[order], facecolors=cols[order], edgecolors=cols[order], linewidths=0.3))
    pts = tris2_all.reshape(-1, 2)
    pad = 0.04 * (pts.max(axis=0) - pts.min(axis=0)).max()
    ax.set_xlim(pts[:, 0].min() - pad, pts[:, 0].max() + pad)
    ax.set_ylim(pts[:, 1].min() - pad, pts[:, 1].max() + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()


def _box_tris(cx: float, cy: float, z0: float, lx: float, ly: float, h: float, yaw: float) -> np.ndarray:
    c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    xs = np.array([-1, 1, 1, -1]) * lx / 2
    ys = np.array([-1, -1, 1, 1]) * ly / 2
    bx, by = cx + c * xs - s * ys, cy + s * xs + c * ys
    bot = np.column_stack([bx, by, np.full(4, z0)])
    top = np.column_stack([bx, by, np.full(4, z0 + h)])
    quads = [bot[::-1], top] + [np.array([bot[i], bot[(i + 1) % 4], top[(i + 1) % 4], top[i]]) for i in range(4)]
    return np.array([t for q in quads for t in (q[[0, 1, 2]], q[[0, 2, 3]])])


def part_render(pn: str = "PF-HB-2201") -> Path:
    part = sample_parts()[pn]
    from pipeforge.fixture import fixture_frame

    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=36, step_deg=3.0)
    frame, off = fixture_frame(part.points, part.clr)
    verts = (frame @ m.vertices.T).T + off
    rot = _view(-30, 34)
    fig, ax = plt.subplots(figsize=(10, 4.2), facecolor=PAPER)
    _render(ax, [(verts[m.faces], STEEL, 0.0)], rot)
    pts = ((frame @ part.points.T).T + off) @ rot.T
    ax.plot(pts[:, 0], pts[:, 1], color=ORANGE, lw=1, ls=(0, (2, 2)), zorder=5)
    ax.scatter(pts[:, 0], pts[:, 1], color=ORANGE, s=10, zorder=6)
    for i, q in enumerate(pts):
        ax.text(q[0], q[1] + 12, f"P{i}", fontsize=7, color=INK, ha="center", zorder=7)
    fig.text(0.01, 0.02, f"{part.part_no}  {part.name}  ·  {part.material}  OD {part.od:g} x t {part.wall:g}  ·  "
             f"CLR {part.radii[0]:g}  ·  cut {part.cut_length():.1f} mm  ·  orange: XYZ intersection points",
             fontsize=8.5, color=INK)
    p = OUT / "part_render.png"
    fig.savefig(p, dpi=160, bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)
    return p


def fixture_render(pn: str = "PF-HB-2201") -> Path:
    part = sample_parts()[pn]
    fx = design_fixture(part)
    m = tube_mesh(part.points, part.clr, part.od, part.wall, segments=28, step_deg=4.0)
    v = (fx.rotation @ m.vertices.T).T + fx.offset
    w, h, t = fx.plate_size
    plate = (_box_tris((fx.plate_min[0] + fx.plate_max[0]) / 2, (fx.plate_min[1] + fx.plate_max[1]) / 2, -t,
                       w, h, t, 0), "#8A9099")
    groups = []
    for b in fx.blocks:
        groups.append((_box_tris(b.contact[0], b.contact[1], 0, b.length, b.width, b.height - part.od / 2, b.yaw_deg),
                       ORANGE if b.datum else "#E9E6DF", 0.0))
    groups.append((v[m.faces], STEEL, 0.0))
    rot = _view(-35, 38)
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor=PAPER)
    _render(ax, groups, rot, base=plate)
    fig.text(0.01, 0.02, f"Checking fixture for {pn}: {len(fx.blocks)} grooved blocks, datum blocks in orange (3-2-1), "
             f"{sum(b.clamp for b in fx.blocks)} clamps, {len(fx.sensors())} sensors", fontsize=8.5, color=INK)
    p = OUT / "fixture_render.png"
    fig.savefig(p, dpi=160, bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)
    return p


def drawing(pn: str = "PF-HB-2201") -> Path:
    part = sample_parts()[pn]
    p = OUT / "drawing.png"
    make_drawing(part.points, part.clr, DrawingInfo(part.part_no, part.name, part.material, part.od, part.wall,
                                                    drawn_by="PipeForge"), pdf_path=p)
    return p


def yamazumi_fig() -> Path:
    from pipeforge import kaizen

    before = baseline_line()
    after = kaizen.smed(kaizen.rebalance(before))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=PAPER)
    colors = {"machine": "#3F5466", "manual": ORANGE, "walk": STEEL}
    for ax, line, title in ((axes[0], before, "Before: end forming over takt"),
                            (axes[1], after, "After rebalancing: every station under takt")):
        rows = yamazumi(line)
        keys = [s.key for s in line.stations]
        bottom = dict.fromkeys(keys, 0.0)
        for r in rows:
            ax.bar(r["station"], r["seconds"], bottom=bottom[r["station"]], color=colors[r["kind"]], edgecolor=PAPER, lw=0.6)
            bottom[r["station"]] += r["seconds"]
        ax.axhline(line.takt_s, color=INK, ls="--", lw=1)
        ax.text(len(keys) - 0.5, line.takt_s + 0.6, f"takt {line.takt_s:.1f} s", ha="right", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_facecolor(PAPER)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("work content (s)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()]
    fig.legend(handles, list(colors), loc="upper center", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    p = OUT / "yamazumi.png"
    fig.savefig(p, dpi=150, facecolor=PAPER)
    plt.close(fig)
    return p


def kaizen_fig() -> Path | None:
    f = ROOT / "artifacts" / "line" / "kaizen_results.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    rows = d["rows"]
    fig, ax = plt.subplots(figsize=(10, 3.8), facecolor=PAPER)
    names = [r["scenario"].split(" ", 1)[1] for r in rows]
    vals = [r["per_day"] for r in rows]
    err = [r["per_day_ci95"] for r in rows]
    ax.bar(names, vals, yerr=err, color=[MUTED] + [ORANGE] * (len(rows) - 1), capsize=3)
    ax.axhline(baseline_line().demand_per_day, color=INK, ls="--", lw=1)
    ax.text(len(rows) - 0.5, baseline_line().demand_per_day + 15, "demand", ha="right", fontsize=8)
    for i, (v, r) in enumerate(zip(vals, rows, strict=True)):
        ax.text(i, v / 2, f"{v:.0f}\nscrap {r['scrap_pct']:.1f}%", ha="center", color="white", fontsize=8)
    ax.set_ylabel("good parts / day")
    ax.set_title(f"Kaizen chain on the synthetic line ({d['reps']} reps x {d['days']:g} days, 95% CI): "
                 f"{d['throughput_gain_pct']:+.1f}% throughput", fontsize=10)
    ax.set_facecolor(PAPER)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    p = OUT / "kaizen.png"
    fig.savefig(p, dpi=150, facecolor=PAPER)
    plt.close(fig)
    return p


def closed_loop_fig() -> Path | None:
    f = ROOT / "artifacts" / "springback" / "closed_loop.json"
    if not f.exists():
        return None
    c = json.loads(f.read_text(encoding="utf-8"))
    names = {"none": "No compensation", "physics": "Physics estimate", "offset": "One constant offset",
             "ml": "ML (setup only)", "ml_in_process": "ML + process signals"}
    styles = {"none": (MUTED, ":"), "physics": (MUTED, "--"), "offset": (STEEL, "-"), "ml": (ORANGE, "-"),
              "ml_in_process": ("#3F5466", "-")}
    fig, ax = plt.subplots(figsize=(6.5, 3.8), facecolor=PAPER)
    for k, curve in c["fpy_by_tolerance"].items():
        tol = [float(x) for x in curve]
        ax.plot(tol, [100 * v for v in curve.values()], marker="o", ms=3, label=names[k], color=styles[k][0],
                ls=styles[k][1])
    ax.set_xlabel("angle tolerance (+/- deg)")
    ax.set_ylabel("% of real bends in tolerance")
    ax.set_title("Closed loop on 315 real TubeBEND bends (out-of-fold)", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.set_facecolor(PAPER)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    p = OUT / "closed_loop.png"
    fig.savefig(p, dpi=150, facecolor=PAPER)
    plt.close(fig)
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (part_render, fixture_render, drawing, yamazumi_fig, kaizen_fig, closed_loop_fig):
        print(fn.__name__, fn())


if __name__ == "__main__":
    main()
