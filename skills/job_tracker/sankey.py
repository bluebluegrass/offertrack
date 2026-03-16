"""Sankey PNG rendering."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skills.job_tracker.types import FunnelMetrics

PAGE_BG = "#FFF7F0"
CARD_BG = "#FFFDF9"
CARD_EDGE = "#F0C8A8"
TITLE_TEXT = "#3F2418"
BODY_TEXT = "#6D4B3A"
MUTED_TEXT = "#9A735E"
ACCENT = "#FF6A3D"
ACCENT_DEEP = "#E9582D"
APPLICATIONS_NODE = "#F1CBB5"
REPLIES_NODE = "#FF8A61"
NO_RESPONSE_NODE = "#E9D6C8"
WITHDRAWN_NODE = "#F7B36A"
OA_NODE = "#F1AA93"
INTERVIEWS_NODE = "#FF7449"
OFFERS_NODE = "#5FAE78"
REJECTED_NODE = "#D9785F"


@dataclass(slots=True)
class Node:
    name: str
    x: float
    y: float
    h: float
    color: str


def _setup_matplotlib() -> None:
    tmp_cache = Path(tempfile.gettempdir()) / "mplcache"
    tmp_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(tmp_cache / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(tmp_cache))


def _curve_path(x0: float, x1: float, y0: float, y1: float):
    from matplotlib.path import Path as MplPath

    c = (x1 - x0) * 0.45
    return [
        (MplPath.MOVETO, (x0, y0)),
        (MplPath.CURVE4, (x0 + c, y0)),
        (MplPath.CURVE4, (x1 - c, y1)),
        (MplPath.CURVE4, (x1, y1)),
    ]


def _draw_flow(ax, x0: float, x1: float, y0_top: float, y0_bot: float, y1_top: float, y1_bot: float, color: str, alpha: float = 0.52):
    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch

    top = _curve_path(x0, x1, y0_top, y1_top)
    bot = _curve_path(x1, x0, y1_bot, y0_bot)

    verts = [pt for _, pt in top] + [pt for _, pt in bot] + [top[0][1]]
    codes = [code for code, _ in top] + [code for code, _ in bot] + [MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=color, edgecolor="none", alpha=alpha))


def _apply_brand_canvas(fig, ax) -> None:
    fig.patch.set_facecolor(PAGE_BG)
    ax.set_facecolor(PAGE_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.axhspan(0.0, 1.0, facecolor=PAGE_BG, zorder=-20)


def _draw_brand_backdrop(ax) -> None:
    from matplotlib.patches import Circle, FancyBboxPatch

    ax.add_patch(Circle((0.10, 0.92), 0.16, facecolor="#FFE5D8", edgecolor="none", alpha=0.85, zorder=-15))
    ax.add_patch(Circle((0.92, 0.12), 0.20, facecolor="#FFF0D9", edgecolor="none", alpha=0.75, zorder=-15))
    ax.add_patch(
        FancyBboxPatch(
            (0.015, 0.10),
            0.97,
            0.80,
            boxstyle="round,pad=0.012,rounding_size=0.03",
            facecolor=CARD_BG,
            edgecolor=CARD_EDGE,
            linewidth=1.4,
            zorder=-10,
        )
    )


def _draw_node(ax, node: Node, node_w: float, value: int, *, emphasis: bool = False) -> None:
    from matplotlib.patches import Rectangle

    rect = Rectangle(
        (node.x - node_w / 2, node.y - node.h / 2),
        node_w,
        node.h,
        facecolor=node.color,
        edgecolor="#FFFFFF",
        linewidth=1.0 if emphasis else 0.8,
        zorder=5,
    )
    ax.add_patch(rect)
    ax.text(
        node.x + 0.038,
        node.y + 0.018,
        str(value),
        fontsize=28 if emphasis else 24,
        fontweight="bold",
        ha="left",
        va="center",
        color=TITLE_TEXT,
    )
    ax.text(
        node.x + 0.038,
        node.y - 0.018,
        node.name,
        fontsize=20 if emphasis else 18,
        ha="left",
        va="center",
        color=BODY_TEXT,
    )


def _draw_title_badge(ax, title: str) -> None:
    ax.text(
        0.5,
        0.06,
        title,
        ha="center",
        va="center",
        fontsize=30,
        fontweight="bold",
        color="#FFFFFF",
        bbox=dict(boxstyle="round,pad=0.42,rounding_size=0.18", facecolor=ACCENT_DEEP, edgecolor="none"),
    )


def _draw_watermark(ax, watermark: str) -> None:
    if not watermark.strip():
        return

    from matplotlib.offsetbox import AnnotationBbox, HPacker, OffsetImage, TextArea

    logo_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "offertracker-icon-transparent.png"
    text = TextArea(
        watermark.strip(),
        textprops={
            "color": MUTED_TEXT,
            "fontsize": 10,
            "ha": "left",
            "va": "center",
        },
    )

    children = [text]
    if logo_path.exists():
        import matplotlib.image as mpimg

        logo = mpimg.imread(str(logo_path))
        children.append(OffsetImage(logo, zoom=0.16))

    packed = HPacker(children=children, align="center", pad=0, sep=5)
    anchored = AnnotationBbox(
        packed,
        (0.985, 0.008),
        xycoords="axes fraction",
        box_alignment=(1, 0),
        frameon=False,
        zorder=20,
    )
    ax.add_artist(anchored)


def render_sankey(metrics: FunnelMetrics, title: str, out_path: str) -> str:
    _setup_matplotlib()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Inter", "Arial", "PingFang SC", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    applications = max(int(metrics.applications), 0)
    replies = max(min(int(metrics.replies), applications), 0)
    no_replies = max(int(metrics.no_replies), 0)
    oa = max(min(int(metrics.oa), replies), 0)
    withdrawn = max(min(int(metrics.withdrawn), max(replies - oa, 0)), 0)
    interviews = max(int(metrics.interviews), 0)
    offers = max(min(int(metrics.offers), interviews), 0)
    rejected = max(int(metrics.rejected), 0)

    oa_to_interviews = min(oa, interviews)
    direct_interviews = max(interviews - oa_to_interviews, 0)
    interview_to_rejected = min(rejected, max(interviews - offers, 0))

    max_total = max(applications, 1)
    # Slightly shorter bars with clearer gaps between stacked stage nodes.
    scale = 0.56 / max_total

    nodes = {
        "applications": Node("Applications", 0.08, 0.50, applications * scale, APPLICATIONS_NODE),
        "replies": Node("Replies", 0.30, 0.80, replies * scale, REPLIES_NODE),
        "no_replies": Node("No Replies", 0.30, 0.40, no_replies * scale, NO_RESPONSE_NODE),
        "withdrawn": Node("Withdrawn", 0.50, 0.78, withdrawn * scale, WITHDRAWN_NODE),
        "oa": Node("OA", 0.50, 0.66, oa * scale, OA_NODE),
        "interviews": Node("Interviews", 0.66, 0.86, interviews * scale, INTERVIEWS_NODE),
        "offers": Node("Offers", 0.86, 0.86, offers * scale, OFFERS_NODE),
        "rejected": Node("Rejected", 0.86, 0.66, rejected * scale, REJECTED_NODE),
    }

    fig, ax = plt.subplots(figsize=(14, 9), dpi=100)
    _apply_brand_canvas(fig, ax)
    _draw_brand_backdrop(ax)

    node_w = 0.024

    def top(node: Node) -> float:
        return node.y + node.h / 2

    out_cursor = {k: top(v) for k, v in nodes.items()}
    in_cursor = {k: top(v) for k, v in nodes.items()}

    def alloc_out(k: str, v: int) -> tuple[float, float]:
        h = v * scale
        y0 = out_cursor[k]
        y1 = y0 - h
        out_cursor[k] = y1
        return y0, y1

    def alloc_in(k: str, v: int) -> tuple[float, float]:
        h = v * scale
        y0 = in_cursor[k]
        y1 = y0 - h
        in_cursor[k] = y1
        return y0, y1

    flows = [
        ("applications", "replies", replies, "#FFB394"),
        ("applications", "no_replies", no_replies, "#F2DED1"),
        ("replies", "oa", oa, "#F8C4AF"),
        ("replies", "withdrawn", withdrawn, "#F9C98D"),
        ("oa", "interviews", oa_to_interviews, "#FFA37F"),
        ("replies", "interviews", direct_interviews, "#FF9470"),
        ("interviews", "offers", offers, "#98D3A8"),
        ("interviews", "rejected", interview_to_rejected, "#E8B09F"),
    ]

    for src, dst, val, color in flows:
        if val <= 0:
            continue
        y0t, y0b = alloc_out(src, val)
        y1t, y1b = alloc_in(dst, val)
        _draw_flow(ax, nodes[src].x + node_w / 2, nodes[dst].x - node_w / 2, y0t, y0b, y1t, y1b, color)

    vals = {
        "applications": applications,
        "replies": replies,
        "no_replies": no_replies,
        "withdrawn": withdrawn,
        "oa": oa,
        "interviews": interviews,
        "offers": offers,
        "rejected": rejected,
    }

    for key, node in nodes.items():
        _draw_node(ax, node, node_w, vals[key], emphasis=(key == "applications"))

    _draw_title_badge(ax, title)
    _draw_watermark(ax, "Generated by OfferTracker")

    output = Path(out_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return str(output)


def render_ai_sankey(
    summary: dict[str, int],
    title: str,
    out_path: str,
    watermark: str = "Generated by OfferTracker",
) -> str:
    """Render Sankey for AI summary with direct-rejection handling and zero-node suppression."""
    _setup_matplotlib()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Inter", "Arial", "PingFang SC", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    applications = max(int(summary.get("applications", 0)), 0)
    interviews = max(int(summary.get("interviews", 0)), 0)
    no_response = max(int(summary.get("no_response", 0)), 0)
    offers = max(int(summary.get("offers", 0)), 0)
    rejected_total = max(int(summary.get("rejections_total", 0)), 0)
    rejected_direct = max(int(summary.get("rejections_without_interview", 0)), 0)
    rejected_after_interview = max(rejected_total - rejected_direct, 0)

    # Clamp to avoid impossible overflows.
    rejected_direct = min(rejected_direct, applications)
    no_response = min(no_response, max(applications - rejected_direct, 0))
    interviews = min(interviews, max(applications - rejected_direct - no_response, 0))
    offers = min(offers, interviews)
    rejected_after_interview = min(rejected_after_interview, max(interviews - offers, 0))

    max_total = max(applications, 1)
    scale = 0.62 / max_total

    stage_x = 0.40
    stage_gap = 0.03
    stage_top = 0.88
    node_defs: dict[str, Node] = {
        "applications": Node("Applications", 0.08, 0.50, applications * scale, APPLICATIONS_NODE),
    }
    stage_cursor = stage_top
    if interviews > 0:
        interviews_h = interviews * scale
        interviews_y = stage_cursor - interviews_h / 2
        node_defs["interviews"] = Node("Interviews", stage_x, interviews_y, interviews_h, INTERVIEWS_NODE)
        stage_cursor -= interviews_h + stage_gap
    if rejected_direct > 0:
        rejected_direct_h = rejected_direct * scale
        rejected_direct_y = stage_cursor - rejected_direct_h / 2
        node_defs["rejected_direct"] = Node("Rejected (Direct)", stage_x, rejected_direct_y, rejected_direct_h, REJECTED_NODE)
        stage_cursor -= rejected_direct_h + stage_gap
    if no_response > 0:
        no_response_h = no_response * scale
        no_response_y = stage_cursor - no_response_h / 2
        node_defs["no_response"] = Node("No Response", stage_x, no_response_y, no_response_h, NO_RESPONSE_NODE)
    if rejected_after_interview > 0:
        node_defs["rejected_after_interview"] = Node(
            "Rejected (After Interview)", 0.70, 0.62, rejected_after_interview * scale, REJECTED_NODE
        )
    if offers > 0:
        node_defs["offers"] = Node("Offers", 0.84, 0.82, offers * scale, OFFERS_NODE)

    fig, ax = plt.subplots(figsize=(14, 9), dpi=100)
    _apply_brand_canvas(fig, ax)
    _draw_brand_backdrop(ax)

    node_w = 0.024

    def top(node: Node) -> float:
        return node.y + node.h / 2

    out_cursor = {k: top(v) for k, v in node_defs.items()}
    in_cursor = {k: top(v) for k, v in node_defs.items()}

    def alloc_out(k: str, v: int) -> tuple[float, float]:
        h = v * scale
        y0 = out_cursor[k]
        y1 = y0 - h
        out_cursor[k] = y1
        return y0, y1

    def alloc_in(k: str, v: int) -> tuple[float, float]:
        h = v * scale
        y0 = in_cursor[k]
        y1 = y0 - h
        in_cursor[k] = y1
        return y0, y1

    flows: list[tuple[str, str, int, str]] = []
    if interviews > 0 and "interviews" in node_defs:
        flows.append(("applications", "interviews", interviews, "#FF9C77"))
    if no_response > 0 and "no_response" in node_defs:
        flows.append(("applications", "no_response", no_response, "#F0DDD0"))
    if rejected_direct > 0 and "rejected_direct" in node_defs:
        flows.append(("applications", "rejected_direct", rejected_direct, "#E7B19F"))
    if offers > 0 and "offers" in node_defs and "interviews" in node_defs:
        flows.append(("interviews", "offers", offers, "#9AD5AA"))
    if rejected_after_interview > 0 and "interviews" in node_defs and "rejected_after_interview" in node_defs:
        flows.append(("interviews", "rejected_after_interview", rejected_after_interview, "#DFA08F"))

    for src, dst, val, color in flows:
        if val <= 0:
            continue
        y0t, y0b = alloc_out(src, val)
        y1t, y1b = alloc_in(dst, val)
        _draw_flow(ax, node_defs[src].x + node_w / 2, node_defs[dst].x - node_w / 2, y0t, y0b, y1t, y1b, color)

    vals = {
        "applications": applications,
        "interviews": interviews,
        "no_response": no_response,
        "offers": offers,
        "rejected_direct": rejected_direct,
        "rejected_after_interview": rejected_after_interview,
    }

    for key, node in node_defs.items():
        _draw_node(ax, node, node_w, vals.get(key, 0), emphasis=(key == "applications"))

    _draw_title_badge(ax, title)
    _draw_watermark(ax, watermark)

    output = Path(out_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return str(output)
