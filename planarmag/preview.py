"""Render a :class:`~planarmag.kicad.Board` to a PNG/SVG preview.

Purely for visual sanity-checking - it draws copper segments coloured per layer
plus the vias and board outline.  Requires matplotlib (an optional extra).
"""

from __future__ import annotations

from .kicad import Board

# A distinct colour per copper layer index (cycles if more layers than colours).
_LAYER_COLORS = [
    "#c83737",  # F.Cu  - red
    "#3a7bd5",  # In1   - blue
    "#2e9e54",  # In2   - green
    "#b8860b",  # In3   - gold
    "#8e44ad",  # In4   - purple
    "#16a085",  # In5   - teal
]


def render_png(board: Board, path: str, *, dpi: int = 150) -> None:
    """Draw ``board`` to ``path`` (``.png`` or ``.svg``)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    layer_name_to_index = {
        board.layer_name(i): i for i in range(board.copper_layers)
    }

    fig, ax = plt.subplots(figsize=(7, 7))
    for s in board.segments:
        idx = layer_name_to_index.get(s.layer, 0)
        color = _LAYER_COLORS[idx % len(_LAYER_COLORS)]
        ax.plot(
            [s.start[0], s.end[0]],
            [s.start[1], s.end[1]],
            color=color,
            linewidth=max(0.6, s.width * 3),
            solid_capstyle="round",
        )

    for v in board.vias:
        ax.add_patch(plt.Circle(v.at, v.size / 2, color="#222222", zorder=5))
        ax.add_patch(plt.Circle(v.at, v.drill / 2, color="#ffffff", zorder=6))

    if board.outline:
        x0, y0, x1, y1 = board.outline
        ax.add_patch(
            plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                          edgecolor="#444444", linewidth=1.0, linestyle="--")
        )

    # board cut-outs (centre-leg hole, pin clearance holes) on Edge.Cuts
    for c in board.circles:
        ax.add_patch(plt.Circle(c.center, c.radius, fill=False,
                                edgecolor="#b08020", linewidth=1.0))
    for p in board.polys:
        ax.add_patch(plt.Polygon(p.points, closed=True, fill=False,
                                 edgecolor="#b08020", linewidth=1.0))

    # legend of copper layers actually used
    used = sorted({layer_name_to_index.get(s.layer, 0) for s in board.segments})
    handles = [
        plt.Line2D([0], [0], color=_LAYER_COLORS[i % len(_LAYER_COLORS)],
                   lw=3, label=board.layer_name(i))
        for i in used
    ]
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8)

    ax.set_aspect("equal")
    ax.set_title(board.title)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
