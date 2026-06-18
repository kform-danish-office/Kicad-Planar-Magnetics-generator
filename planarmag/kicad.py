"""Minimal writer for KiCad ``.kicad_pcb`` board files.

This emits the KiCad 9/10 s-expression format (file version 20241229) directly,
so no KiCad installation or ``pcbnew`` Python module is required to *generate*
boards - you only need KiCad to open the result.

Only the handful of primitives a magnetics generator needs are supported:
copper track segments, vias, a board outline (Edge.Cuts), silkscreen text and
net declarations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .geometry import Point

# --- Copper layer numbering -------------------------------------------------
# KiCad 9/10 renumbered copper layers relative to KiCad <= 8.  In the current
# format F.Cu is id 0, B.Cu is id 2, and inner layers In{k}.Cu are 2*k + 2.
F_CU_ID = 0
B_CU_ID = 2


def copper_layer_name(index: int, total: int) -> str:
    """Name of the ``index``-th copper layer (0 = top) in an ``total``-layer stack."""
    if not 0 <= index < total:
        raise IndexError(f"layer index {index} out of range for {total}-layer board")
    if index == 0:
        return "F.Cu"
    if index == total - 1:
        return "B.Cu"
    return f"In{index}.Cu"


def _copper_layer_id(index: int, total: int) -> int:
    if index == 0:
        return F_CU_ID
    if index == total - 1:
        return B_CU_ID
    return 2 * index + 2


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Segment:
    start: Point
    end: Point
    width: float
    layer: str
    net: int


@dataclass
class Via:
    at: Point
    size: float
    drill: float
    layers: tuple[str, str]
    net: int


@dataclass
class Text:
    text: str
    at: Point
    layer: str
    size: float = 1.0
    thickness: float = 0.15


@dataclass
class GrCircle:
    center: Point
    radius: float
    layer: str = "Edge.Cuts"


@dataclass
class GrPoly:
    points: list[Point]
    layer: str = "Edge.Cuts"


@dataclass
class Net:
    number: int
    name: str


@dataclass
class Board:
    """An in-memory board that can serialise itself to ``.kicad_pcb`` text."""

    copper_layers: int = 2
    thickness: float = 1.6
    title: str = "Planar Magnetic"
    segments: list[Segment] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    circles: list[GrCircle] = field(default_factory=list)
    polys: list[GrPoly] = field(default_factory=list)
    nets: list[Net] = field(default_factory=lambda: [Net(0, "")])
    outline: tuple[float, float, float, float] | None = None  # xmin,ymin,xmax,ymax

    def __post_init__(self) -> None:
        # KiCad only loads boards with an even number of copper layers.
        if self.copper_layers < 2 or self.copper_layers % 2 != 0:
            raise ValueError(
                f"copper_layers must be even and >= 2 (KiCad requirement); "
                f"got {self.copper_layers}. Use the next even number."
            )

    # -- construction helpers ------------------------------------------------
    def add_net(self, name: str) -> int:
        number = len(self.nets)
        self.nets.append(Net(number, name))
        return number

    def layer_name(self, index: int) -> str:
        return copper_layer_name(index, self.copper_layers)

    def add_track(self, pts: list[Point], width: float, layer_index: int, net: int) -> None:
        layer = self.layer_name(layer_index)
        for a, b in zip(pts, pts[1:]):
            self.segments.append(Segment(a, b, width, layer, net))

    def add_via(
        self,
        at: Point,
        net: int,
        *,
        size: float = 0.6,
        drill: float = 0.3,
        from_layer: int = 0,
        to_layer: int | None = None,
    ) -> None:
        to_layer = self.copper_layers - 1 if to_layer is None else to_layer
        self.vias.append(
            Via(
                at,
                size,
                drill,
                (self.layer_name(from_layer), self.layer_name(to_layer)),
                net,
            )
        )

    def add_text(self, text: str, at: Point, *, layer_index: int = 0, size: float = 1.0) -> None:
        layer = "F.SilkS" if layer_index == 0 else "B.SilkS"
        self.texts.append(Text(text, at, layer, size=size))

    def set_outline(self, xmin: float, ymin: float, xmax: float, ymax: float) -> None:
        self.outline = (xmin, ymin, xmax, ymax)

    def add_circle(self, center: Point, radius: float, *, layer: str = "Edge.Cuts") -> None:
        """Add a circle (e.g. a round centre-leg cutout) on ``layer``."""
        self.circles.append(GrCircle(center, radius, layer))

    def add_polygon(self, points: list[Point], *, layer: str = "Edge.Cuts") -> None:
        """Add a closed polygon (e.g. a rectangular cutout) on ``layer``."""
        self.polys.append(GrPoly(points, layer))

    def content_bbox(self) -> tuple[float, float, float, float] | None:
        """Bounding box over copper, vias, text and Edge.Cuts cut-outs.

        Reference geometry on other layers (e.g. a core outline on Cmts.User) is
        ignored so it doesn't inflate the board edge.
        """
        xs: list[float] = []
        ys: list[float] = []
        for s in self.segments:
            xs += [s.start[0], s.end[0]]
            ys += [s.start[1], s.end[1]]
        for v in self.vias:
            xs += [v.at[0] - v.size / 2, v.at[0] + v.size / 2]
            ys += [v.at[1] - v.size / 2, v.at[1] + v.size / 2]
        for t in self.texts:
            xs.append(t.at[0]); ys.append(t.at[1])
        for c in self.circles:
            if c.layer == "Edge.Cuts":
                xs += [c.center[0] - c.radius, c.center[0] + c.radius]
                ys += [c.center[1] - c.radius, c.center[1] + c.radius]
        for p in self.polys:
            if p.layer == "Edge.Cuts":
                xs += [pt[0] for pt in p.points]
                ys += [pt[1] for pt in p.points]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    # -- serialisation -------------------------------------------------------
    def _layers_block(self) -> str:
        lines = ['\t(layers']
        # copper layers, top to bottom, in the order KiCad expects (F, inner, B)
        for i in range(self.copper_layers):
            lines.append(
                f'\t\t({_copper_layer_id(i, self.copper_layers)} '
                f'"{copper_layer_name(i, self.copper_layers)}" signal)'
            )
        # the technical layers a board needs to be valid / openable
        tech = [
            (9, "F.Adhes", "user", "F.Adhesive"),
            (11, "B.Adhes", "user", "B.Adhesive"),
            (13, "F.Paste", "user", None),
            (15, "B.Paste", "user", None),
            (5, "F.SilkS", "user", "F.Silkscreen"),
            (7, "B.SilkS", "user", "B.Silkscreen"),
            (1, "F.Mask", "user", None),
            (3, "B.Mask", "user", None),
            (17, "Dwgs.User", "user", "User.Drawings"),
            (19, "Cmts.User", "user", "User.Comments"),
            (21, "Eco1.User", "user", "User.Eco1"),
            (23, "Eco2.User", "user", "User.Eco2"),
            (25, "Edge.Cuts", "user", None),
            (27, "Margin", "user", None),
            (31, "F.CrtYd", "user", "F.Courtyard"),
            (29, "B.CrtYd", "user", "B.Courtyard"),
            (35, "F.Fab", "user", None),
            (33, "B.Fab", "user", None),
        ]
        for lid, name, kind, alias in tech:
            if alias:
                lines.append(f'\t\t({lid} "{name}" {kind} "{alias}")')
            else:
                lines.append(f'\t\t({lid} "{name}" {kind})')
        lines.append('\t)')
        return "\n".join(lines)

    def _net_blocks(self) -> str:
        return "\n".join(f'\t(net {n.number} "{n.name}")' for n in self.nets)

    def _segment_block(self, s: Segment) -> str:
        return (
            "\t(segment\n"
            f"\t\t(start {s.start[0]:.4f} {s.start[1]:.4f})\n"
            f"\t\t(end {s.end[0]:.4f} {s.end[1]:.4f})\n"
            f"\t\t(width {s.width:.4f})\n"
            f'\t\t(layer "{s.layer}")\n'
            f"\t\t(net {s.net})\n"
            f'\t\t(uuid "{_uuid()}")\n'
            "\t)"
        )

    def _via_block(self, v: Via) -> str:
        return (
            "\t(via\n"
            f"\t\t(at {v.at[0]:.4f} {v.at[1]:.4f})\n"
            f"\t\t(size {v.size:.4f})\n"
            f"\t\t(drill {v.drill:.4f})\n"
            f'\t\t(layers "{v.layers[0]}" "{v.layers[1]}")\n'
            f"\t\t(net {v.net})\n"
            f'\t\t(uuid "{_uuid()}")\n'
            "\t)"
        )

    def _text_block(self, t: Text) -> str:
        return (
            f'\t(gr_text "{t.text}"\n'
            f"\t\t(at {t.at[0]:.4f} {t.at[1]:.4f})\n"
            f'\t\t(layer "{t.layer}")\n'
            f'\t\t(uuid "{_uuid()}")\n'
            "\t\t(effects\n"
            f"\t\t\t(font (size {t.size:.3f} {t.size:.3f}) (thickness {t.thickness:.3f}))\n"
            "\t\t)\n"
            "\t)"
        )

    def _circle_block(self, c: GrCircle) -> str:
        edge = (c.center[0] + c.radius, c.center[1])
        return (
            "\t(gr_circle\n"
            f"\t\t(center {c.center[0]:.4f} {c.center[1]:.4f})\n"
            f"\t\t(end {edge[0]:.4f} {edge[1]:.4f})\n"
            "\t\t(stroke (width 0.1) (type solid))\n"
            "\t\t(fill no)\n"
            f'\t\t(layer "{c.layer}")\n'
            f'\t\t(uuid "{_uuid()}")\n'
            "\t)"
        )

    def _poly_block(self, p: GrPoly) -> str:
        pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in p.points)
        return (
            "\t(gr_poly\n"
            f"\t\t(pts {pts})\n"
            "\t\t(stroke (width 0.1) (type solid))\n"
            "\t\t(fill no)\n"
            f'\t\t(layer "{p.layer}")\n'
            f'\t\t(uuid "{_uuid()}")\n'
            "\t)"
        )

    def _outline_blocks(self) -> str:
        if self.outline is None:
            return ""
        x0, y0, x1, y1 = self.outline
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        out = []
        for a, b in zip(corners, corners[1:]):
            out.append(
                "\t(gr_line\n"
                f"\t\t(start {a[0]:.4f} {a[1]:.4f})\n"
                f"\t\t(end {b[0]:.4f} {b[1]:.4f})\n"
                '\t\t(stroke (width 0.1) (type solid))\n'
                '\t\t(layer "Edge.Cuts")\n'
                f'\t\t(uuid "{_uuid()}")\n'
                "\t)"
            )
        return "\n".join(out)

    def to_string(self) -> str:
        parts = [
            "(kicad_pcb",
            "\t(version 20241229)",
            '\t(generator "planarmag")',
            '\t(generator_version "1.0")',
            "\t(general",
            f"\t\t(thickness {self.thickness})",
            "\t)",
            '\t(paper "A4")',
            "\t(title_block",
            f'\t\t(title "{self.title}")',
            "\t)",
            self._layers_block(),
            "\t(setup",
            "\t)",
            self._net_blocks(),
        ]
        outline = self._outline_blocks()
        if outline:
            parts.append(outline)
        parts.extend(self._circle_block(c) for c in self.circles)
        parts.extend(self._poly_block(p) for p in self.polys)
        parts.extend(self._segment_block(s) for s in self.segments)
        parts.extend(self._via_block(v) for v in self.vias)
        parts.extend(self._text_block(t) for t in self.texts)
        parts.append(")")
        return "\n".join(parts) + "\n"

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_string())
