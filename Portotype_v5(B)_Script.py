"""
Laser-cut tapered box generator
Run this INSIDE Blender's Scripting tab (Text Editor > Run Script).
It will:
  1. Build every part as a 2D outline (with box-joint style male tabs / female slots)
  2. Lay all parts out on a single sheet (no overlaps, fixed spacing)
  3. Write a ready-to-cut .svg file to OUTPUT_PATH
  4. (Optional) also draw the parts as curve objects in the Blender scene for a visual preview

Only edit the PARAMETERS section below.
"""

import bpy
import math
import os

# ============================================================
# PARAMETERS  (all lengths in mm)
# ============================================================

a = 210.0   # base length (long edge)
b = 75.0    # depth (constant across the whole box)
c = 32.0    # panel4 vertical height (the "cuboid" part)
d = 64.0    # panel4 slant edge length (the "trapezoid" part)
slant_angle_deg = 30.0

thickness = 5.0   # material thickness
kerf = 0.1        # laser kerf

tab_width = 10.0   # male tab width (along the edge)
tab_depth = 10.0   # male tab protrusion length (perpendicular to the edge)
slot_len = 10.0    # female slot length (along the edge)   -> matches tab_width
slot_width = 5.0   # female slot width  (matches material thickness)
slot_offset = tab_depth / 2.0   # distance from edge to slot centerline (default assumption)

circle_dia = 19.1     # Piece2 hole diameter
tri_side = 32.0       # equilateral triangle side (hole centers)
tri_gap = 10.0        # perpendicular gap from Top-mating b-edge to nearest point of apex circle

sheet_w = 400.0
sheet_h = 500.0
part_spacing = 5.0

OUTPUT_PATH = bpy.path.abspath("//laser_cut_parts.svg")  # saved next to the .blend file
DRAW_PREVIEW_IN_BLENDER = True

# ============================================================
# DERIVED VALUES
# ============================================================

rad = math.radians(slant_angle_deg)
e = a - 2 * d * math.cos(rad)          # top edge length
panel4_h = c + d * math.sin(rad)       # total height of panel4

# tab/slot fit compensation using kerf (keeps joints snug, not loose)
tab_width_cut = tab_width - kerf
tab_depth_cut = tab_depth  # protrusion length itself isn't kerf-critical
slot_len_cut = slot_len + kerf
slot_width_cut = slot_width + kerf

# ============================================================
# GEOMETRY HELPERS
# ============================================================

def polygon_centroid(pts):
    x = sum(p[0] for p in pts) / len(pts)
    y = sum(p[1] for p in pts) / len(pts)
    return (x, y)


def outward_normal(p_start, p_end, centroid):
    """Unit normal to edge (p_start->p_end), pointing away from the polygon centroid."""
    ex, ey = p_end[0] - p_start[0], p_end[1] - p_start[1]
    elen = math.hypot(ex, ey)
    ex, ey = ex / elen, ey / elen
    nx, ny = ey, -ex
    mid = ((p_start[0] + p_end[0]) / 2.0, (p_start[1] + p_end[1]) / 2.0)
    to_mid = (mid[0] - centroid[0], mid[1] - centroid[1])
    if nx * to_mid[0] + ny * to_mid[1] < 0:
        nx, ny = -nx, -ny
    return (nx, ny)


def evenly_spaced_positions(length, n):
    """n positions along [0, length], evenly spread including symmetric end margins."""
    return [length * (i + 1) / (n + 1) for i in range(n)]


def tabbed_edge(p_start, p_end, n_tabs, tab_w, tab_d, outward):
    """Returns polyline points from p_start to p_end (inclusive) with n_tabs
    rectangular male tabs protruding outward along the way."""
    ex, ey = p_end[0] - p_start[0], p_end[1] - p_start[1]
    elen = math.hypot(ex, ey)
    ux, uy = ex / elen, ey / elen
    nx, ny = outward
    positions = evenly_spaced_positions(elen, n_tabs)
    pts = [p_start]
    half = tab_w / 2.0
    for pos in positions:
        cx = p_start[0] + ux * pos
        cy = p_start[1] + uy * pos
        p1 = (cx - ux * half, cy - uy * half)
        p2 = (p1[0] + nx * tab_d, p1[1] + ny * tab_d)
        p3 = (cx + ux * half + nx * tab_d, cy + uy * half + ny * tab_d)
        p4 = (cx + ux * half, cy + uy * half)
        pts += [p1, p2, p3, p4]
    pts.append(p_end)
    return pts


def slot_holes(p_start, p_end, n_slots, slot_l, slot_w, offset, inward):
    """Returns list of 4-point rectangles (closed holes) centered along the edge,
    offset into the material by `offset` along `inward`."""
    ex, ey = p_end[0] - p_start[0], p_end[1] - p_start[1]
    elen = math.hypot(ex, ey)
    ux, uy = ex / elen, ey / elen
    nx, ny = inward
    positions = evenly_spaced_positions(elen, n_slots)
    holes = []
    hl, hw = slot_l / 2.0, slot_w / 2.0
    for pos in positions:
        cx = p_start[0] + ux * pos + nx * offset
        cy = p_start[1] + uy * pos + ny * offset
        rect = [
            (cx - ux * hl - nx * hw, cy - uy * hl - ny * hw),
            (cx + ux * hl - nx * hw, cy + uy * hl - ny * hw),
            (cx + ux * hl + nx * hw, cy + uy * hl + ny * hw),
            (cx - ux * hl + nx * hw, cy - uy * hl + ny * hw),
        ]
        holes.append(rect)
    return holes


def build_piece(vertices, edge_specs):
    """vertices: polygon corners in order.
    edge_specs[i] = ('male', n) | ('female', n) | ('plain', None)
    describing the edge from vertices[i] to vertices[(i+1) % N]."""
    centroid = polygon_centroid(vertices)
    outline = []
    holes = []
    n_v = len(vertices)
    for i in range(n_v):
        p_start = vertices[i]
        p_end = vertices[(i + 1) % n_v]
        kind, n = edge_specs[i]
        normal = outward_normal(p_start, p_end, centroid)
        if kind == 'male':
            pts = tabbed_edge(p_start, p_end, n, tab_width_cut, tab_depth_cut, normal)
            outline.extend(pts[:-1])
        elif kind == 'female':
            inward = (-normal[0], -normal[1])
            hs = slot_holes(p_start, p_end, n, slot_len_cut, slot_width_cut, slot_offset, inward)
            holes.extend(hs)
            outline.append(p_start)
        else:
            outline.append(p_start)
    return {'outline': outline, 'holes': holes}


def bbox(outline):
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return min(xs), min(ys), max(xs), max(ys)


def translate_piece(piece, dx, dy):
    outline = [(x + dx, y + dy) for x, y in piece['outline']]
    holes = [[(x + dx, y + dy) for x, y in h] for h in piece['holes']]
    return {'outline': outline, 'holes': holes, 'name': piece.get('name', '')}


# ============================================================
# BUILD EACH PART
# ============================================================

parts = []

# --- Base: a x b, all 4 edges male ---
verts = [(0, 0), (a, 0), (a, b), (0, b)]
specs = [('male', 4), ('male', 2), ('male', 4), ('male', 2)]
base = build_piece(verts, specs)
base['name'] = 'Base'
parts.append(base)

# --- Top: e x b, e-edges male (mate panel4), b-edges female (mate Piece2) ---
verts = [(0, 0), (e, 0), (e, b), (0, b)]
specs = [('male', 2), ('female', 2), ('male', 2), ('female', 2)]
top = build_piece(verts, specs)
top['name'] = 'Top'
parts.append(top)

# --- Piece1 (x2): c x b. c-edges male x1 (mate panel4 front/back).
#     one b-edge female (mate Base), other b-edge female (mate Piece2) ---
verts = [(0, 0), (c, 0), (c, b), (0, b)]
specs = [('male', 1), ('female', 2), ('male', 1), ('female', 2)]
piece1_shape = build_piece(verts, specs)
for i in range(2):
    p = dict(piece1_shape)
    p['name'] = f'Piece1_{i+1}'
    parts.append(p)

# --- Piece2 (x2): d x b. All edges male.
#     d-edges (mate panel4 slants), b-edges (mate Top and Piece1) ---
verts = [(0, 0), (d, 0), (d, b), (0, b)]
specs = [('male', 2), ('male', 2), ('male', 2), ('male', 2)]
piece2_shape = build_piece(verts, specs)

# 3 circle holes: apex points toward the LEFT edge (x=0), which mates Top
r = circle_dia / 2.0
apex_dist = tri_gap + r
tri_height = tri_side * math.sqrt(3) / 2.0
c1 = (apex_dist, b / 2.0)
c2 = (apex_dist + tri_height, b / 2.0 - tri_side / 2.0)
c3 = (apex_dist + tri_height, b / 2.0 + tri_side / 2.0)
piece2_shape['circles'] = [c1, c2, c3]
piece2_shape['circle_r'] = r

for i in range(2):
    p = dict(piece2_shape)
    p['name'] = f'Piece2_{i+1}'
    parts.append(p)

# --- Panel4 (x2): hexagon, ALL edges female ---
dx = d * math.cos(rad)
dy = d * math.sin(rad)
V0 = (0, 0)
V1 = (a, 0)
V2 = (a, c)
V3 = (a - dx, c + dy)
V4 = (dx, c + dy)
V5 = (0, c)
verts = [V0, V1, V2, V3, V4, V5]
specs = [
    ('female', 4),  # V0-V1 bottom (a)      -> mates Base
    ('female', 1),  # V1-V2 right vertical  -> mates Piece1
    ('female', 2),  # V2-V3 right slant     -> mates Piece2
    ('female', 2),  # V3-V4 top (e)         -> mates Top
    ('female', 2),  # V4-V5 left slant      -> mates Piece2 (mirror)
    ('female', 1),  # V5-V0 left vertical   -> mates Piece1 (mirror)
]
panel4_shape = build_piece(verts, specs)
for i in range(2):
    p = dict(panel4_shape)
    p['name'] = f'Panel4_{i+1}'
    parts.append(p)

# ============================================================
# SHEET LAYOUT (simple shelf packer)
# ============================================================

def pack_parts(parts, sheet_w, sheet_h, spacing):
    placed = []
    boxes = []
    for p in parts:
        minx, miny, maxx, maxy = bbox(p['outline'])
        boxes.append((maxx - minx, maxy - miny, minx, miny, p))
    boxes.sort(key=lambda t: -t[1])  # tallest first

    x_cursor = spacing
    y_cursor = spacing
    row_height = 0

    for w, h, minx, miny, p in boxes:
        if x_cursor + w + spacing > sheet_w:
            x_cursor = spacing
            y_cursor += row_height + spacing
            row_height = 0
        if y_cursor + h + spacing > sheet_h:
            raise RuntimeError(
                f"Sheet too small: '{p.get('name','?')}' doesn't fit "
                f"({sheet_w}x{sheet_h}mm sheet, {spacing}mm spacing)."
            )
        dx = x_cursor - minx
        dy = y_cursor - miny
        placed.append(translate_piece(p, dx, dy))
        if 'circles' in p:
            placed[-1]['circles'] = [(cx + dx, cy + dy) for cx, cy in p['circles']]
            placed[-1]['circle_r'] = p['circle_r']
        x_cursor += w + spacing
        row_height = max(row_height, h)

    return placed


placed_parts = pack_parts(parts, sheet_w, sheet_h, part_spacing)

# ============================================================
# SVG EXPORT
# ============================================================

def polygon_to_path(points):
    d = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in points) + " Z"
    return d


def write_svg(parts, sheet_w, sheet_h, path):
    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_w}mm" height="{sheet_h}mm" '
        f'viewBox="0 0 {sheet_w} {sheet_h}">'
    )
    lines.append(
        f'<rect x="0" y="0" width="{sheet_w}" height="{sheet_h}" '
        f'fill="none" stroke="none"/>'
    )
    for p in parts:
        d = polygon_to_path(p['outline'])
        lines.append(f'<path d="{d}" fill="none" stroke="#000000" stroke-width="0.1"/>')
        for h in p['holes']:
            hd = polygon_to_path(h)
            lines.append(f'<path d="{hd}" fill="none" stroke="#ff0000" stroke-width="0.1"/>')
        if 'circles' in p:
            for cx, cy in p['circles']:
                lines.append(
                    f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{p["circle_r"]:.3f}" '
                    f'fill="none" stroke="#0000ff" stroke-width="0.1"/>'
                )
    lines.append('</svg>')

    with open(path, 'w') as f:
        f.write("\n".join(lines))

    print(f"SVG written to: {path}")


write_svg(placed_parts, sheet_w, sheet_h, OUTPUT_PATH)

# ============================================================
# OPTIONAL: preview curves inside Blender
# ============================================================

def draw_preview(parts):
    coll_name = "LaserCutParts_Preview"
    if coll_name in bpy.data.collections:
        old = bpy.data.collections[coll_name]
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(coll)

    def make_curve(name, loops):
        curve_data = bpy.data.curves.new(name, type='CURVE')
        curve_data.dimensions = '2D'
        for loop in loops:
            spline = curve_data.splines.new('POLY')
            spline.points.add(len(loop) - 1)
            for i, (x, y) in enumerate(loop):
                spline.points[i].co = (x / 1000.0, y / 1000.0, 0, 1)  # mm -> m
            spline.use_cyclic_u = True
        obj = bpy.data.objects.new(name, curve_data)
        coll.objects.link(obj)

    for p in parts:
        loops = [p['outline']] + p['holes']
        if 'circles' in p:
            for cx, cy in p['circles']:
                r = p['circle_r']
                circ = [
                    (cx + r * math.cos(t), cy + r * math.sin(t))
                    for t in [i * math.tau / 32 for i in range(32)]
                ]
                loops.append(circ)
        make_curve(p['name'], loops)


if DRAW_PREVIEW_IN_BLENDER:
    draw_preview(placed_parts)

print(f"Panel4: e={e:.3f}mm, height={panel4_h:.3f}mm")
print(f"Total parts placed: {len(placed_parts)}")
