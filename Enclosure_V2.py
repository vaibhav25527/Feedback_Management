import bpy
import math
import os

# ============================================================================
# Enclosure_V3 - Feedback Management Hardware Enclosure
# Two-part body (rectangular cuboid lower section + trapezoidal-prism upper
# section) with ESP32 mount, horizontal M3 self-tapping screw retention via
# corner gussets integrated into the enclosure wall, and embossed SVG logo.
# ============================================================================

# ---------- 0. Scene reset ----------
def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = 'MILLIMETERS'

# ---------- 1. Parameters (all mm) ----------
wall        = 5.6
base_wall   = 5.6
L_slant     = 89.0
base_angle  = 30.0   # updated 2026-07-22: slant angle of the upper trapezoid
                      # section, measured from horizontal (was 60.0). Slant
                      # edge length L_slant is kept fixed per spec, so the
                      # trapezoid's height and top width both change as a
                      # result of this angle change.
hole_dia    = 19.0
hole_radius = hole_dia / 2.0

box_width   = 209.0  # widened from 160.0 -> top face is now 120mm x 100mm (landscape) for the logo
depth       = 100.0

cuboid_height = 40.0  # NEW 2026-07-22: height of the rectangular lower
                       # section. The trapezoidal section now sits on top
                       # of this cuboid instead of the body being a single
                       # trapezoid all the way down.

# Triangular button layout spacing (locked, do not change)
btn_row_gap   = 30.0
btn_apex_rise = 26.0

# Horizontal screw parameters (M3 self-tapping, no heat-set inserts)
screw_dia    = 3.0
screw_len    = 8.0
screw_radius = screw_dia / 2.0

# ESP32 bed & pillar parameters
esp_w = 27.94 + 0.4
esp_l = 50.8 + 0.4
esp_h = 4.0
peg_dia = 2.55  # updated from 2.3 -- verify fit against real ESP32 dev-kit hole spacing

# PSU cutout
psu_len = 12.5
psu_brd = 6.25

# Logo emboss height
logo_emboss_height = 2.3

angle_rad    = math.radians(base_angle)
H            = L_slant * math.sin(angle_rad)   # height of the trapezoid section only (not the whole body anymore)
run          = L_slant * math.cos(angle_rad)
top_width    = box_width - 2 * run
total_height = cuboid_height + H                # NEW: total exterior body height above the base plate

# Trapezoid-section inner offset (perpendicular wall thickness on a sloped
# face requires a larger horizontal offset than the wall thickness itself).
inner_bottom_w = box_width - 2 * (wall / math.sin(angle_rad))
inner_top_w    = inner_bottom_w - 2 * run

# Cuboid-section inner offset (vertical wall -> horizontal offset = wall).
# NOTE: this is intentionally different from inner_bottom_w above (which
# uses the sloped-wall formula) - the two meet at a small internal ledge
# where the cuboid transitions into the trapezoid, since a wall of uniform
# thickness measured perpendicular to each surface is wider in plan at a
# vertical wall than at a 30 deg sloped wall. This is expected, not a bug.
inner_cuboid_w = box_width - 2 * wall

# ---------- 2. Geometry helpers ----------
def make_trapezoid_prism(name, bottom_w, top_w, height, y0, y1, z0=0.0):
    verts = [
        (-bottom_w / 2, y0, z0), (bottom_w / 2, y0, z0),
        (bottom_w / 2, y1, z0), (-bottom_w / 2, y1, z0),
        (-top_w / 2, y0, z0 + height), (top_w / 2, y0, z0 + height),
        (top_w / 2, y1, z0 + height), (-top_w / 2, y1, z0 + height),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (1, 2, 6, 5), (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

def slant_point(side_multiplier, u, v):
    """ side_multiplier: 1 for Right (+X), -1 for Left (-X).
    v is measured up the slant starting where the trapezoid section begins
    (i.e. from the top of the cuboid section), not from the base plate. """
    x = side_multiplier * (box_width / 2 - v * math.cos(angle_rad))
    y = u
    z = base_wall + cuboid_height + v * math.sin(angle_rad)
    return x, y, z

# ---------- 3. Boolean helpers ----------
def add_boolean(target, other, op='DIFFERENCE'):
    """Apply a boolean op and immediately clean up: apply the modifier and
    delete the helper/cutter object. This keeps every body a single, clean,
    printable mesh with no leftover cutter geometry cluttering the interior
    or the outliner."""
    mod = target.modifiers.new(f"{op.title()}_{other.name}", 'BOOLEAN')
    mod.operation = op
    mod.object = other
    other.hide_set(True)

    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(other, do_unlink=True)

# ---------- 4. Body generation (outer shell + hollow cavity) ----------
def build_body():
    # Outer shell: rectangular cuboid lower section + trapezoidal-prism
    # upper section, fused into one solid.
    outer = make_trapezoid_prism("Enclosure_Body", box_width, box_width,
                                  cuboid_height, 0, depth, base_wall)
    outer_trapezoid = make_trapezoid_prism("Body_Outer_Trapezoid", box_width, top_width,
                                            H, 0, depth, base_wall + cuboid_height)
    add_boolean(outer, outer_trapezoid, 'UNION')

    # Hollow cavity, cut as two matching pieces (lower cuboid + upper
    # trapezoid) so wall thickness is correct on both the vertical lower
    # walls and the 30 deg upper walls. The pieces overlap slightly at the
    # seam (seam_overlap) so the two DIFFERENCE cuts leave no uncut sliver
    # where the sections meet.
    seam_overlap = 2.0

    inner_cuboid_h = cuboid_height + 5.0 + seam_overlap
    inner_cuboid = make_trapezoid_prism("Body_Inner_Cavity_Lower", inner_cuboid_w, inner_cuboid_w,
                                         inner_cuboid_h, wall, depth - wall, base_wall - 5.0)
    add_boolean(outer, inner_cuboid, 'DIFFERENCE')

    inner_trap_h = (H - wall) + 5.0 + seam_overlap
    inner_trap = make_trapezoid_prism("Body_Inner_Cavity_Upper", inner_bottom_w, inner_top_w,
                                       inner_trap_h, wall, depth - wall,
                                       base_wall + cuboid_height - seam_overlap)
    add_boolean(outer, inner_trap, 'DIFFERENCE')

    return outer

# ---------- 5. Buttons (triangular layout, locked - do not modify) ----------
def add_buttons(body):
    slant_u_center = depth / 2
    slant_v_center = L_slant / 2

    triangular_layout = [
        (slant_u_center - btn_row_gap / 2, slant_v_center + btn_apex_rise / 2),  # base left (rotated)
        (slant_u_center + btn_row_gap / 2, slant_v_center + btn_apex_rise / 2),  # base right (rotated)
        (slant_u_center,                   slant_v_center - btn_apex_rise / 2),  # apex (bottom)
    ]

    for i, (u, v) in enumerate(triangular_layout):
        x, y, z = slant_point(1, u, v)
        bpy.ops.mesh.primitive_cylinder_add(radius=hole_radius, depth=wall * 10, location=(x, y, z))
        cutter = bpy.context.active_object
        cutter.name = f"Right_Slant_Button_{i}"
        cutter.rotation_euler = (0, angle_rad, 0)
        add_boolean(body, cutter, 'DIFFERENCE')

    for i, (u, v) in enumerate(triangular_layout):
        x, y, z = slant_point(-1, u, v)
        bpy.ops.mesh.primitive_cylinder_add(radius=hole_radius, depth=wall * 10, location=(x, y, z))
        cutter = bpy.context.active_object
        cutter.name = f"Left_Slant_Button_{i}"
        cutter.rotation_euler = (0, -angle_rad, 0)
        add_boolean(body, cutter, 'DIFFERENCE')

# ---------- 6. PSU cutout (back wall, Y = depth) ----------
def add_psu_cutout(body):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, depth, base_wall + psu_brd / 2 + 2))
    psu_cutter = bpy.context.active_object
    psu_cutter.name = "PSU_Cutout"
    psu_cutter.scale = (psu_len, wall * 4, psu_brd)
    add_boolean(body, psu_cutter, 'DIFFERENCE')

# ---------- 7. Base plate ----------
def build_base_plate():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, depth / 2, base_wall / 2))
    base_plate = bpy.context.active_object
    base_plate.name = "Base_Plate"
    base_plate.scale = (box_width, depth, base_wall)
    return base_plate

# ---------- 8. ESP32 mount (fused into base plate, one printable body) ----------
# Connector clearance: the ESP32's USB/power port needs a path out of the bed
# toward the PSU cutout in the back wall. Width is an estimate (typical
# USB-C/micro-USB clearance) - replace connector_notch_w with the real
# measurement if available.
connector_notch_w = 15.0

def add_esp_mount(base_plate):
    bed_w, bed_l, bed_h, nest_depth = esp_w + 5.0, esp_l + 5.0, 6.0, 4.0
    esp_y = depth - wall - (bed_l / 2) - 2.0

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, esp_y, base_wall + bed_h / 2))
    esp_bed = bpy.context.active_object
    esp_bed.name = "ESP32_Bed"
    esp_bed.scale = (bed_w, bed_l, bed_h)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, esp_y, base_wall + bed_h - nest_depth / 2 + 0.1))
    nest_cut = bpy.context.active_object
    nest_cut.scale = (esp_w, esp_l, nest_depth + 0.2)
    add_boolean(esp_bed, nest_cut, 'DIFFERENCE')

    # Notch through the bed's back-facing lip (toward Y = depth), lined up
    # with the PSU cutout, so the USB/power connector on the board has a
    # clear path out instead of being boxed in by the raised bed wall.
    notch_y = esp_y + bed_l / 2
    notch_z = base_wall + bed_h - nest_depth / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, notch_y, notch_z))
    connector_notch = bpy.context.active_object
    connector_notch.name = "ESP_Connector_Notch"
    connector_notch.scale = (connector_notch_w, 10.0, nest_depth + 2.0)
    add_boolean(esp_bed, connector_notch, 'DIFFERENCE')

    # Fuse bed directly into the base plate - single printable body
    add_boolean(base_plate, esp_bed, 'UNION')

    # 4 mounting pillars inside the bed
    peg_margin = 2.0
    pillar_height = nest_depth - 1.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            px = sx * (esp_w / 2 - peg_margin)
            py = esp_y + sy * (esp_l / 2 - peg_margin)
            pz = base_wall + (bed_h - nest_depth) + pillar_height / 2

            bpy.ops.mesh.primitive_cylinder_add(radius=peg_dia / 2, depth=pillar_height, location=(px, py, pz))
            peg = bpy.context.active_object
            peg.name = f"ESP_Pillar_{sx}_{sy}"
            add_boolean(base_plate, peg, 'UNION')

# ---------- 9. Screw system (vertical, holes integrated into the body wall) ----------
# Redesigned 2026-07-22: the four cylindrical screw bosses are gone. Each
# screw's shaft hole is now bored directly into a local gusset that is
# flush with, and fused into, the two real outer walls that meet at that
# corner of the cuboid section - i.e. the reinforcement reads as a thicker
# corner of the actual enclosure wall, not a separate free-standing post
# hanging in the cavity. Hole X/Y positions (and therefore the matching
# base plate holes, which are computed from the same corner list) are
# unchanged from the previous boss-based design.
#
# Base plate (thickness = base_wall, ~5.6-6mm) gets a stepped hole from the
# BOTTOM face:
#   - head pocket: 3mm deep x 3mm dia (screw head seats here, flush/recessed)
#   - pilot hole: remaining plate thickness x 1.9mm dia (shaft passes through)
# The body gets a solid corner gusset fused to its two nearest outer walls,
# with a blind 1.9mm dia pilot hole bored up into it from the bottom, sized
# to take the portion of the screw shaft (~5-6mm) that continues past the
# base plate. Screw is 8-9mm total: 3mm seats in the base plate, the rest
# bites into the wall gusset.
corner_margin = 15.0  # inset of the screw-hole center from the plate edges, clears ESP bed comfortably

head_pocket_depth = 3.0
head_pocket_dia   = 3.0
pilot_dia         = 1.9
screw_total_len   = 8.5  # 8-9mm screw

corner_block_size   = corner_margin + 6.0  # gusset extent from the real wall inward, encloses the pilot hole
                                            # with margin - verify against ESP bed clearance once meshed in Blender
corner_block_height = 7.0                  # gusset height, hangs from the body's bottom inner face like the old boss did

def add_screw_system(body, base_plate):
    plate_thickness = base_wall
    pilot_depth_in_plate = plate_thickness - head_pocket_depth
    shaft_in_body = screw_total_len - head_pocket_depth  # remaining shaft above the base plate

    corner_x = box_width / 2 - corner_margin
    # (hole_x, hole_y, wall_sign_x, wall_y) - wall_sign_x is which side
    # wall (+X/-X) this corner sits against; wall_y is which front/back
    # wall (y=0 or y=depth) it sits against. The gusset is built flush
    # against both.
    corners = [
        (-corner_x, corner_margin,        -1, 0),
        ( corner_x, corner_margin,         1, 0),
        (-corner_x, depth - corner_margin, -1, depth),
        ( corner_x, depth - corner_margin,  1, depth),
    ]

    for i, (px, py, wall_sign_x, wall_y) in enumerate(corners):
        # --- Base plate: head pocket, bored up from the bottom face (z=0) ---
        pocket_z = head_pocket_depth / 2
        bpy.ops.mesh.primitive_cylinder_add(radius=head_pocket_dia / 2, depth=head_pocket_depth + 0.2,
                                             location=(px, py, pocket_z))
        pocket = bpy.context.active_object
        pocket.name = f"Screw_Head_Pocket_{i}"
        add_boolean(base_plate, pocket, 'DIFFERENCE')

        # --- Base plate: pilot hole through the remaining thickness ---
        pilot_z = head_pocket_depth + pilot_depth_in_plate / 2
        bpy.ops.mesh.primitive_cylinder_add(radius=pilot_dia / 2, depth=pilot_depth_in_plate + 0.2,
                                             location=(px, py, pilot_z))
        pilot = bpy.context.active_object
        pilot.name = f"Screw_Pilot_Plate_{i}"
        add_boolean(base_plate, pilot, 'DIFFERENCE')

        # --- Body: corner gusset, flush with and fused into the two real
        # walls meeting at this corner, UNION'd onto the body ---
        block_cx = wall_sign_x * (box_width / 2 - corner_block_size / 2)
        block_cy = (corner_block_size / 2) if wall_y == 0 else (depth - corner_block_size / 2)
        block_cz = base_wall + corner_block_height / 2

        bpy.ops.mesh.primitive_cube_add(size=1, location=(block_cx, block_cy, block_cz))
        gusset = bpy.context.active_object
        gusset.name = f"Screw_Corner_Gusset_{i}"
        gusset.scale = (corner_block_size, corner_block_size, corner_block_height)
        add_boolean(body, gusset, 'UNION')

        # --- Body gusset: blind pilot hole bored up from the bottom for the shaft ---
        bore_depth = min(shaft_in_body, corner_block_height - 0.5)
        bore_z = base_wall + bore_depth / 2
        bpy.ops.mesh.primitive_cylinder_add(radius=pilot_dia / 2, depth=bore_depth + 0.2, location=(px, py, bore_z))
        bore = bpy.context.active_object
        bore.name = f"Screw_Pilot_Shaft_{i}"
        add_boolean(body, bore, 'DIFFERENCE')

# ---------- 10. Logo (embossed SVG on top surface) ----------
def _find_view3d_context():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
    return None, None

def add_logo(body):
    import traceback

    logo_path = os.path.join(os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd(), "logo.svg")
    if not os.path.exists(logo_path):
        print(f"[Enclosure_V3] logo.svg not found at {logo_path} - skipping logo emboss.")
        return

    area, region = _find_view3d_context()
    if area is None:
        print("[Enclosure_V3] No VIEW_3D area found - logo operators may fail without it.")

    imported = []
    try:
        ctx = bpy.context.temp_override(area=area, region=region) if area else _NullContext()
        with ctx:
            bpy.ops.import_curve.svg(filepath=logo_path)
            imported = [o for o in bpy.context.selected_objects if o.type == 'CURVE']
            if not imported:
                print("[Enclosure_V3] SVG import returned no curves - skipping logo emboss.")
                return

            bpy.ops.object.select_all(action='DESELECT')
            for o in imported:
                o.select_set(True)
            bpy.context.view_layer.objects.active = imported[0]
            bpy.ops.object.join()

            logo = bpy.context.active_object
            bpy.ops.object.convert(target='MESH')
            logo = bpy.context.active_object

            # Auto-fit: scale the logo to fit within a margin of the flat
            # top face (top_width x depth), preserving aspect ratio.
            bpy.context.view_layer.update()
            dim_x, dim_y = logo.dimensions.x, logo.dimensions.y
            if dim_x <= 0.0001 or dim_y <= 0.0001:
                raise RuntimeError(f"Imported logo has degenerate dimensions ({dim_x}, {dim_y}) - aborting emboss.")

            target_w = top_width * 0.55
            target_h = depth * 0.35
            scale_factor = min(target_w / dim_x, target_h / dim_y)
            logo.scale = (scale_factor, scale_factor, 1.0)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            bpy.context.view_layer.update()
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.extrude_region_move(
                TRANSFORM_OT_translate={"value": (0, 0, logo_emboss_height)}
            )
            bpy.ops.object.mode_set(mode='OBJECT')

            logo.location = (0, depth / 2, base_wall + total_height - 0.01)

            add_boolean(body, logo, 'UNION')
            print(f"[Enclosure_V3] Logo embossed successfully - fitted to {dim_x*scale_factor:.1f} x {dim_y*scale_factor:.1f} mm.")

    except Exception as e:
        print(f"[Enclosure_V3] Logo emboss failed: {e}")
        traceback.print_exc()
        # Clean up any partially-imported/converted objects so a failed
        # logo attempt doesn't clutter the scene.
        for o in list(imported):
            if o and o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
        active = bpy.context.view_layer.objects.active
        if active and active.name in bpy.data.objects and active not in (body,):
            if active.type in ('CURVE', 'MESH') and active.name.lower().startswith(('curve', 'logo')):
                bpy.data.objects.remove(active, do_unlink=True)

class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False

# ---------- 11. Cleanup / viewport ----------
def cleanup_view(base_plate):
    # Exploded view: drop base plate below the body so both are visible
    base_plate.location.z -= 40.0

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.view3d.view_all()

# ---------- 12. Main ----------
def main():
    reset_scene()
    body = build_body()
    add_buttons(body)
    add_psu_cutout(body)
    base_plate = build_base_plate()
    add_esp_mount(base_plate)
    add_screw_system(body, base_plate)
    add_logo(body)
    cleanup_view(base_plate)

main()
