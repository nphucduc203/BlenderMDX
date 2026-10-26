import bpy
import mathutils
import math
import os
import tempfile
from PIL import Image
from . import constants
from . import blp


# Session cache for indexed textures
_TEXTURE_INDEX_CACHE = {}

WC3_EMITTERS_CACHE = {}

FILTER_MODE_NAMES = {
    0: 'none',          # Opaque
    1: 'transparent',   # Alpha Cutoff (0.75)
    2: 'blend',         # Alpha Blend
    3: 'additive',      # Additive
    4: 'add_alpha',     # AddAlpha
    5: 'modulate',      # Modulate (Multiply)
    6: 'modulate_2x',   # Modulate 2X
}


def get_preferences():
    if __package__ and __package__ in bpy.context.preferences.addons:
        return bpy.context.preferences.addons[__package__].preferences
    for key in ('io_scene_warcraft_3', 'plugin'):
        if key in bpy.context.preferences.addons:
            return bpy.context.preferences.addons[key].preferences
    for key, val in bpy.context.preferences.addons.items():
        if 'warcraft' in key.lower() or 'mdx' in key.lower():
            return val.preferences
    return None


def get_blp_cache_dir():
    cache_dir = os.path.join(tempfile.gettempdir(), 'wc3_blp_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def create_fcurve(action, datablock, data_path, index=0):
    if hasattr(action, 'fcurves'):
        return action.fcurves.new(data_path=data_path, index=index)
    else:
        if datablock.animation_data is None:
            datablock.animation_data_create()
        if datablock.animation_data.action != action:
            datablock.animation_data.action = action
        return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)


def get_texture_index(root_dirs):
    """
    Build a fast dictionary index of all textures in root_dirs.
    Key: lower-case filename (and lower-case relative path), Value: full absolute path.
    """
    global _TEXTURE_INDEX_CACHE
    index = {}
    valid_exts = {'.blp', '.png', '.tga', '.dds', '.jpg', '.jpeg', '.bmp'}

    for root in root_dirs:
        if not root or not os.path.isdir(root):
            continue
        root_abs = os.path.abspath(root)
        if root_abs in _TEXTURE_INDEX_CACHE:
            index.update(_TEXTURE_INDEX_CACHE[root_abs])
            continue

        dir_cache = {}
        try:
            for dirpath, dirnames, filenames in os.walk(root_abs):
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        full_p = os.path.join(dirpath, f)
                        dir_cache[f.lower()] = full_p
                        try:
                            rel_p = os.path.relpath(full_p, root_abs).replace('/', os.sep).replace('\\', os.sep).lower()
                            dir_cache[rel_p] = full_p
                        except ValueError:
                            pass
        except Exception:
            pass

        _TEXTURE_INDEX_CACHE[root_abs] = dir_cache
        index.update(dir_cache)

    return index


def find_texture_file(image_filename, mdx_file_path, importProperties):
    """
    Search for a texture file matching image_filename (.blp, .png, etc.) across:
    1. importProperties.texture_search_dir (if provided)
    2. Folder of the .mdx file and its parent/grandparent directories (e.g. Work/)
    3. Preferences resourceFolder and alternativeResourceFolder
    """
    if not image_filename:
        return None

    clean_name = image_filename.replace('/', os.sep).replace('\\', os.sep)
    base_name = os.path.basename(clean_name)
    stem, ext = os.path.splitext(base_name)
    if not ext:
        ext = '.blp'

    mdx_dir = os.path.dirname(os.path.abspath(mdx_file_path)) if mdx_file_path else ''
    parent_dir = os.path.dirname(mdx_dir) if mdx_dir else ''
    grandparent_dir = os.path.dirname(parent_dir) if parent_dir else ''

    search_roots = []

    custom_dir = getattr(importProperties, 'texture_search_dir', '')
    if custom_dir and os.path.isdir(str(custom_dir)):
        search_roots.append(str(custom_dir))

    if mdx_dir and os.path.isdir(mdx_dir):
        search_roots.append(mdx_dir)
    if parent_dir and os.path.isdir(parent_dir):
        search_roots.append(parent_dir)
    if grandparent_dir and os.path.isdir(grandparent_dir):
        search_roots.append(grandparent_dir)

    pref = get_preferences()
    if pref:
        for p_dir in [getattr(pref, 'resourceFolder', ''), getattr(pref, 'alternativeResourceFolder', '')]:
            p_dir_str = str(p_dir).strip()
            if p_dir_str and os.path.isdir(p_dir_str):
                search_roots.append(p_dir_str)

    for s_dir in search_roots:
        cand_rel = os.path.join(s_dir, clean_name)
        if os.path.isfile(cand_rel):
            return cand_rel
        cand_base = os.path.join(s_dir, base_name)
        if os.path.isfile(cand_base):
            return cand_base
        cand_tex_sub = os.path.join(s_dir, 'Textures', base_name)
        if os.path.isfile(cand_tex_sub):
            return cand_tex_sub
        cand_tex_lower = os.path.join(s_dir, 'textures', base_name)
        if os.path.isfile(cand_tex_lower):
            return cand_tex_lower
        cand_imp_sub = os.path.join(s_dir, 'war3mapImported', base_name)
        if os.path.isfile(cand_imp_sub):
            return cand_imp_sub

    tex_index = get_texture_index(search_roots)

    key_clean = clean_name.lower()
    if key_clean in tex_index:
        return tex_index[key_clean]

    key_base = base_name.lower()
    if key_base in tex_index:
        return tex_index[key_base]

    for alt_ext in ['.blp', '.png', '.tga', '.dds', '.jpg', '.jpeg']:
        alt_key = (stem + alt_ext).lower()
        if alt_key in tex_index:
            return tex_index[alt_key]

    return None


def create_solid_color_image(name, color_rgba, width=32, height=32):
    b_img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
    pixels = list(color_rgba) * (width * height)
    b_img.pixels.foreach_set(pixels)
    b_img.pack()
    return b_img


def load_or_convert_texture(found_path, tex_name):
    """
    Given a found file path, if it's .blp, convert to cached PNG via custom BLP decoder,
    load into Blender, and pack. If it's already an image, load directly and pack.
    """
    ext = os.path.splitext(found_path)[1].lower()

    if ext == '.blp':
        try:
            cache_dir = get_blp_cache_dir()
            mtime = int(os.path.getmtime(found_path))
            size = os.path.getsize(found_path)
            cache_file = os.path.join(cache_dir, f"{tex_name}_{mtime}_{size}.png")
            if not os.path.exists(cache_file) or os.path.getsize(cache_file) == 0:
                blp.blp_to_png(found_path, cache_file)

            b_img = bpy.data.images.load(cache_file)
            b_img.name = tex_name
            b_img['wc3_cache_png'] = cache_file
            b_img.pack()
            return b_img
        except Exception as e:
            print(f"[WarCraft 3] Error converting BLP {found_path}: {e}")
            return None
    else:
        try:
            b_img = bpy.data.images.load(found_path)
            b_img.name = tex_name
            b_img['wc3_cache_png'] = found_path
            b_img.pack()
            return b_img
        except Exception as e:
            print(f"[WarCraft 3] Error loading image {found_path}: {e}")
            return None


def _blender_image_to_pil(b_img):
    """Convert a Blender bpy.types.Image to a PIL RGBA Image."""
    if not b_img:
        return None
    cached_path = b_img.get('wc3_cache_png', None)
    if cached_path and os.path.isfile(str(cached_path)):
        try:
            return Image.open(str(cached_path)).convert('RGBA')
        except Exception:
            pass
    w, h = b_img.size[0], b_img.size[1]
    if w <= 0 or h <= 0:
        return None
    raw = list(b_img.pixels)
    rgba_bytes = bytearray(w * h * 4)
    for i in range(w * h):
        r = int(max(min(raw[i * 4 + 0] * 255.0, 255), 0))
        g = int(max(min(raw[i * 4 + 1] * 255.0, 255), 0))
        b = int(max(min(raw[i * 4 + 2] * 255.0, 255), 0))
        a = int(max(min(raw[i * 4 + 3] * 255.0, 255), 0))
        rgba_bytes[i * 4 + 0] = r
        rgba_bytes[i * 4 + 1] = g
        rgba_bytes[i * 4 + 2] = b
        rgba_bytes[i * 4 + 3] = a
    pil_img = Image.frombytes('RGBA', (w, h), bytes(rgba_bytes))
    return pil_img.transpose(Image.FLIP_TOP_BOTTOM)


def composite_team_color_over_texture(team_color_rgb, overlay_b_img, composite_name):
    """
    Composite a Layer 0 TeamColor (ReplaceableId 1) + Layer 1 Blend Texture into a single
    RGBA PNG texture so glTF export displays Team Color + Unit Armor with zero z-fighting.
    """
    existing = bpy.data.images.get(composite_name)
    if existing:
        return existing

    pil_over = _blender_image_to_pil(overlay_b_img)
    if pil_over is None:
        return overlay_b_img

    w, h = pil_over.size
    r_tc = int(max(min(team_color_rgb[0] * 255.0, 255), 0))
    g_tc = int(max(min(team_color_rgb[1] * 255.0, 255), 0))
    b_tc = int(max(min(team_color_rgb[2] * 255.0, 255), 0))

    bg = Image.new('RGBA', (w, h), (r_tc, g_tc, b_tc, 255))
    comp = Image.alpha_composite(bg, pil_over)

    cache_dir = get_blp_cache_dir()
    safe_fname = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in composite_name)
    out_path = os.path.join(cache_dir, f"{safe_fname}.png")
    comp.save(out_path, 'PNG')

    b_img = bpy.data.images.load(out_path)
    b_img.name = composite_name
    b_img['wc3_cache_png'] = out_path
    b_img.pack()
    return b_img


def bake_alpha_to_rgb_for_additive_texture(src_b_img, tint_rgb=(1.0, 1.0, 1.0), layer_alpha=1.0):
    """
    Convert a WarCraft 3 Additive (FilterMode 3) or AddAlpha (FilterMode 4) texture into an
    UN-PREMULTIPLIED RGBA PNG texture for standard glTF `alphaMode: BLEND`:
    - Why UN-PREMULTIPLIED?
      In a radial glow texture like `2 (95)_11.blp`, the outer 70% of the image has dark pixels
      (`RGB = 10..40`) fading to black (`0,0,0`).
      In standard glTF `alphaMode: BLEND`, the GPU blends:
         `FinalColor = src.rgb * src.a + dst.rgb * (1 - src.a)`
      If `src.rgb` is dark (`10..40`) while `src.a` is `0.15`, the GPU multiplies `dst.rgb * 0.85`
      and adds almost nothing (`src.rgb * 0.15`), which DARKENS the background into a black box
      (especially when 21 glow quads stack on top of each other like `Geoset[17]`: `0.85^10 = 0.19` -> 81% BLACK!).
    - By normalizing `src.rgb = (r / lum) * tint` so `src.rgb` is ALWAYS pure bright color (even in the
      faintest outer fringe!) and putting `(lum ** 2.0) * tex_a * layer_alpha` in `src.a` (with a hard
      zero threshold for `lum < 0.08`), the outer black box is 100% transparent (`Alpha = 0`) and
      the soft glow fringe NEVER darkens the character underneath!
    """
    t_key = f"{tint_rgb[0]:.2f}_{tint_rgb[1]:.2f}_{tint_rgb[2]:.2f}_{layer_alpha:.2f}"
    baked_name = f"GLTF_UnpremGlow_{src_b_img.name}_{t_key}"
    existing = bpy.data.images.get(baked_name)
    if existing:
        return existing

    pil_src = _blender_image_to_pil(src_b_img)
    if pil_src is None:
        return src_b_img

    w, h = pil_src.size
    src_px = pil_src.load()
    out_img = Image.new('RGBA', (w, h))
    out_px = out_img.load()

    tr, tg, tb = tint_rgb[0], tint_rgb[1], tint_rgb[2]
    la = max(min(float(layer_alpha), 1.0), 0.05)
    base_r = int(max(min(255.0 * tr, 255.0), 0.0))
    base_g = int(max(min(255.0 * tg, 255.0), 0.0))
    base_b = int(max(min(255.0 * tb, 255.0), 0.0))

    for y in range(h):
        for x in range(w):
            r, g, b, a = src_px[x, y]
            lum = max(r, g, b) / 255.0
            if lum < 0.06 or a < 5:
                out_px[x, y] = (base_r, base_g, base_b, 0)
            else:
                nr = int(max(min((r / lum) * tr, 255.0), 0.0))
                ng = int(max(min((g / lum) * tg, 255.0), 0.0))
                nb = int(max(min((b / lum) * tb, 255.0), 0.0))
                eff_a = (lum ** 1.8) * (a / 255.0) * la
                na = int(max(min(eff_a * 255.0, 255.0), 0.0))
                out_px[x, y] = (nr, ng, nb, na)

    cache_dir = get_blp_cache_dir()
    safe_fname = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in baked_name)
    out_path = os.path.join(cache_dir, f"{safe_fname}.png")
    out_img.save(out_path, 'PNG')

    b_img = bpy.data.images.load(out_path)
    b_img.name = baked_name
    b_img['wc3_cache_png'] = out_path
    b_img.pack()
    return b_img


def is_inverted_outline_shell(model, geoset_idx):
    """
    Detect whether a Geoset in `model` is an Inverted-Hull Rim/Outline Shell (such as Geosets
    10, 11, 12, 13 on custom HeroMoonPriestess models) whose vertex normals intentionally point
    INWARD (dot product < -0.5 against the base body mesh).
    """
    if geoset_idx < 0 or geoset_idx >= len(model.meshes):
        return False
    g = model.meshes[geoset_idx]
    if g.material_id is None or g.material_id >= len(model.materials):
        return False
    mat = model.materials[g.material_id]
    if not mat.layers:
        return False
    l0 = mat.layers[0]
    if len(mat.layers) != 1 or not (l0.shading_flags & 0x1) or (l0.shading_flags & 0x10):
        return False

    g_bones = set(g.vertex_groups_ids or [])
    for other_idx, other in enumerate(model.meshes):
        if other_idx == geoset_idx or len(other.vertices) < len(g.vertices):
            continue
        if not (g_bones & set(other.vertex_groups_ids or [])):
            continue
        dots = []
        sample_count = min(30, len(g.vertices))
        for v, n in zip(g.vertices[:sample_count], g.normals[:sample_count]):
            best_d = 999999.0
            best_n = (0.0, 0.0, 1.0)
            for ov, on in zip(other.vertices, other.normals):
                d = (v[0] - ov[0]) ** 2 + (v[1] - ov[1]) ** 2 + (v[2] - ov[2]) ** 2
                if d < best_d:
                    best_d = d
                    best_n = on
            if best_d < 36.0:
                dots.append(n[0] * best_n[0] + n[1] * best_n[1] + n[2] * best_n[2])
        if len(dots) >= 5 and (sum(dots) / len(dots)) < -0.5:
            return True
    return False


def is_stacked_additive_halo_cloud(model, geoset_idx):
    """
    Detect whether a Geoset is a cloud of multiple overlapping Additive Halo Quads (such as
    `Geoset[17]` in `HeroMoonPriestess`, which consists of 21 large intersecting 4-vertex planes
    using `FilterMode 3` Additive with low alpha `<= 0.35`).
    In Warcraft 3's hardware Additive Blend (`GL_ONE, GL_ONE`), 21 intersecting black-bordered
    planes add a faint golden haze. In glTF (which ONLY supports `alphaMode: BLEND`, NOT additive),
    21 intersecting planes in `DITHERED` or `BLENDED` mode cause severe depth-sorting occlusion
    and black screen walls in front of the character (`image_fca83d.jpg`)!
    """
    if geoset_idx < 0 or geoset_idx >= len(model.meshes):
        return False
    g = model.meshes[geoset_idx]
    if g.material_id is None or g.material_id >= len(model.materials):
        return False
    mat = model.materials[g.material_id]
    if not mat.layers:
        return False
    l0 = mat.layers[0]
    if l0.filter_mode not in (3, 4):
        return False
    # Check if geometry is composed entirely of disconnected quads (4 vertices per 2 triangles)
    if len(g.vertices) >= 16 and len(g.vertices) % 4 == 0 and len(g.triangles) == (len(g.vertices) // 2):
        return True
    return False


def make_action_cyclic(action):
    if not action:
        return
    if hasattr(action, 'fcurves'):
        for fc in action.fcurves:
            try:
                mod = fc.modifiers.new('CYCLES')
                mod.mode_after = 'REPEAT'
                mod.mode_before = 'REPEAT'
            except Exception:
                pass
    elif hasattr(action, 'layers'):
        for layer in action.layers:
            for strip in getattr(layer, 'strips', []):
                for cb in getattr(strip, 'channelbags', []):
                    for fc in getattr(cb, 'fcurves', []):
                        try:
                            mod = fc.modifiers.new('CYCLES')
                            mod.mode_after = 'REPEAT'
                            mod.mode_before = 'REPEAT'
                        except Exception:
                            pass


def animate_texture_animations(model, bpyMaterials, frameTime):
    if not getattr(model, 'texture_animations', None):
        return
    for mat_idx, bpyMat in enumerate(bpyMaterials):
        if not bpyMat or not bpyMat.node_tree:
            continue
        for node in bpyMat.node_tree.nodes:
            if node.type == 'MAPPING' and node.name.startswith('Mapping_Mat'):
                try:
                    parts = node.name.split('_')
                    m_id = int(parts[1].replace('Mat', ''))
                    l_id = int(parts[2].replace('L', ''))
                    if m_id >= len(model.materials):
                        continue
                    mat_def = model.materials[m_id]
                    if l_id >= len(mat_def.layers):
                        continue
                    layer_def = mat_def.layers[l_id]
                    if layer_def.texture_animation_id is None:
                        continue
                    ta_id = layer_def.texture_animation_id
                    if ta_id >= len(model.texture_animations):
                        continue
                    ta = model.texture_animations[ta_id]
                    if ta.translations and ta.translations.tracks_count > 0:
                        for k in range(ta.translations.tracks_count):
                            time_ms = ta.translations.times[k]
                            val = ta.translations.values[k]
                            frame = round(time_ms / frameTime, 2)
                            node.inputs['Location'].default_value = (val[0], -val[1], val[2])
                            node.inputs['Location'].keyframe_insert('default_value', index=0, frame=frame)
                            node.inputs['Location'].keyframe_insert('default_value', index=1, frame=frame)
                        if bpyMat.node_tree.animation_data:
                            make_action_cyclic(bpyMat.node_tree.animation_data.action)
                except Exception as e:
                    print(f"[WarCraft 3] Error animating texture: {e}")


def purge_orphaned_wc3_actions():
    """Purge orphaned actions created by this addon."""
    existing_armatures = {obj.name for obj in bpy.data.objects if obj.type == 'ARMATURE'}
    existing_meshes = {obj.name for obj in bpy.data.objects if obj.type == 'MESH'}
    for act in list(bpy.data.actions):
        arm_tag = act.get('wc3_armature_name', None)
        obj_tag = act.get('wc3_object_name', None)
        if arm_tag is None and obj_tag is None:
            continue
        if arm_tag and arm_tag not in existing_armatures:
            try:
                bpy.data.actions.remove(act)
            except Exception:
                pass
        elif obj_tag and obj_tag not in existing_meshes:
            try:
                bpy.data.actions.remove(act)
            except Exception:
                pass
        elif act.users == 0:
            try:
                bpy.data.actions.remove(act)
            except Exception:
                pass


def create_particle_emitter_systems(model, armatureObject, bone_names, bpyImages, global_scale=0.03):
    """
    Convert Warcraft 3 ParticleEmitter2 into functional Blender particle systems
    (exact original node setup preserved for 100% Blender compatibility).
    """
    if not getattr(model, 'particle_emitters_2', None):
        return []

    col_name = "WarCraft 3 Particles"
    part_col = bpy.data.collections.get(col_name)
    if not part_col:
        part_col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(part_col)

    inst_col_name = "WarCraft 3 Particle Instances"
    inst_col = bpy.data.collections.get(inst_col_name)
    if not inst_col:
        inst_col = bpy.data.collections.new(inst_col_name)
        part_col.children.link(inst_col)
    inst_col.hide_viewport = True
    inst_col.hide_render = True

    s = global_scale
    created_systems = []
    bonesByObjectId = {node.node.id: bone_names[index] for index, node in enumerate(model.nodes)}

    for emitter_idx, emitter in enumerate(model.particle_emitters_2):
        bone_name = bonesByObjectId.get(emitter.node.id) if emitter.node else None
        if bone_name is None:
            continue
        emitter_name = emitter.node.name or f"Emitter_{emitter_idx}"

        pw = max(emitter.width * 0.5 * s, 0.15)
        pl = max(emitter.length * 0.5 * s, 0.15)
        bb_verts = [(-pw, 0.0, -pl), (pw, 0.0, -pl), (pw, 0.0, pl), (-pw, 0.0, pl)]
        bb_faces = [(0, 1, 2, 3)]
        bb_mesh = bpy.data.meshes.new(f"W3_Quad_{emitter_name}_{emitter_idx}")
        bb_mesh.from_pydata(bb_verts, (), bb_faces)

        bb_mesh.uv_layers.new()
        uv_layer = bb_mesh.uv_layers.active.data
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for loop in bb_mesh.loops:
            uv_layer[loop.index].uv = uvs[loop.vertex_index]

        bb_obj = bpy.data.objects.new(f"W3_Inst_{emitter_name}_{emitter_idx}", bb_mesh)
        bb_obj.location = (0.0, 0.0, -1000.0)
        inst_col.objects.link(bb_obj)

        mat_name = f"W3_PartMat_{emitter_name}_{emitter_idx}"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        mat.use_backface_culling = False
        if hasattr(mat, 'blend_method'):
            mat.blend_method = 'BLEND'
        if hasattr(mat, 'surface_render_method'):
            mat.surface_render_method = 'BLENDED'
        if hasattr(mat, 'show_transparent_back'):
            mat.show_transparent_back = True

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        out_node = nodes.new('ShaderNodeOutputMaterial')
        out_node.location = (700, 0)

        p_info = nodes.new('ShaderNodeParticleInfo')
        p_info.location = (-900, 200)

        div_t = nodes.new('ShaderNodeMath')
        div_t.operation = 'DIVIDE'
        div_t.location = (-700, 200)
        links.new(p_info.outputs['Age'], div_t.inputs[0])
        links.new(p_info.outputs['Lifetime'], div_t.inputs[1])

        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.location = (-450, 200)
        c0 = emitter.segment_colors[0] if len(emitter.segment_colors) > 0 else (1.0, 1.0, 1.0)
        c1 = emitter.segment_colors[1] if len(emitter.segment_colors) > 1 else (1.0, 1.0, 1.0)
        c2 = emitter.segment_colors[2] if len(emitter.segment_colors) > 2 else (1.0, 1.0, 1.0)
        a0 = (emitter.segment_alphas[0] / 255.0) if len(emitter.segment_alphas) > 0 else 1.0
        a1 = (emitter.segment_alphas[1] / 255.0) if len(emitter.segment_alphas) > 1 else 1.0
        a2 = (emitter.segment_alphas[2] / 255.0) if len(emitter.segment_alphas) > 2 else 0.0

        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = (c0[0], c0[1], c0[2], a0)
        ramp.color_ramp.elements[1].position = 1.0
        ramp.color_ramp.elements[1].color = (c2[0], c2[1], c2[2], a2)
        t_mid = getattr(emitter, 'time_middle', 0.5)
        if t_mid <= 0.0 or t_mid >= 1.0:
            t_mid = 0.5
        mid_el = ramp.color_ramp.elements.new(max(min(t_mid, 0.95), 0.05))
        mid_el.color = (c1[0], c1[1], c1[2], a1)
        links.new(div_t.outputs['Value'], ramp.inputs['Fac'])

        tex_img = bpyImages[emitter.texture_id] if (0 <= emitter.texture_id < len(bpyImages)) else None
        cols = max(emitter.columns, 1)
        rows = max(emitter.rows, 1)

        if cols > 1 or rows > 1:
            t_coord = nodes.new('ShaderNodeTexCoord')
            t_coord.location = (-900, -200)
            sep_uv = nodes.new('ShaderNodeSeparateXYZ')
            sep_uv.location = (-700, -200)
            links.new(t_coord.outputs['UV'], sep_uv.inputs['Vector'])

            tot_frames = float(cols * rows)
            mul_f = nodes.new('ShaderNodeMath')
            mul_f.operation = 'MULTIPLY'
            mul_f.inputs[1].default_value = tot_frames
            mul_f.location = (-500, -200)
            links.new(div_t.outputs['Value'], mul_f.inputs[0])

            flr_f = nodes.new('ShaderNodeMath')
            flr_f.operation = 'FLOOR'
            flr_f.location = (-350, -200)
            links.new(mul_f.outputs['Value'], flr_f.inputs[0])

            mod_c = nodes.new('ShaderNodeMath')
            mod_c.operation = 'MODULO'
            mod_c.inputs[1].default_value = float(cols)
            mod_c.location = (-200, -100)
            links.new(flr_f.outputs['Value'], mod_c.inputs[0])

            div_r = nodes.new('ShaderNodeMath')
            div_r.operation = 'DIVIDE'
            div_r.inputs[1].default_value = float(cols)
            div_r.location = (-200, -300)
            links.new(flr_f.outputs['Value'], div_r.inputs[0])

            flr_r = nodes.new('ShaderNodeMath')
            flr_r.operation = 'FLOOR'
            flr_r.location = (-50, -300)
            links.new(div_r.outputs['Value'], flr_r.inputs[0])

            add_u = nodes.new('ShaderNodeMath')
            add_u.operation = 'ADD'
            add_u.location = (-50, -100)
            links.new(sep_uv.outputs['X'], add_u.inputs[0])
            links.new(mod_c.outputs['Value'], add_u.inputs[1])

            div_u = nodes.new('ShaderNodeMath')
            div_u.operation = 'DIVIDE'
            div_u.inputs[1].default_value = float(cols)
            div_u.location = (100, -100)
            links.new(add_u.outputs['Value'], div_u.inputs[0])

            sub_r = nodes.new('ShaderNodeMath')
            sub_r.operation = 'SUBTRACT'
            sub_r.inputs[0].default_value = float(rows - 1)
            sub_r.location = (100, -300)
            links.new(flr_r.outputs['Value'], sub_r.inputs[1])

            add_v = nodes.new('ShaderNodeMath')
            add_v.operation = 'ADD'
            add_v.location = (250, -300)
            links.new(sep_uv.outputs['Y'], add_v.inputs[0])
            links.new(sub_r.outputs['Value'], add_v.inputs[1])

            div_v = nodes.new('ShaderNodeMath')
            div_v.operation = 'DIVIDE'
            div_v.inputs[1].default_value = float(rows)
            div_v.location = (400, -300)
            links.new(add_v.outputs['Value'], div_v.inputs[0])

            comb = nodes.new('ShaderNodeCombineXYZ')
            comb.location = (550, -200)
            links.new(div_u.outputs['Value'], comb.inputs['X'])
            links.new(div_v.outputs['Value'], comb.inputs['Y'])

            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = tex_img
            tex_node.location = (700, -200)
            links.new(comb.outputs['Vector'], tex_node.inputs['Vector'])
        else:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = tex_img
            tex_node.location = (-150, -100)

        if emitter.filter_mode == 1:
            add_shader = nodes.new('ShaderNodeAddShader')
            add_shader.location = (450, 0)
            transp = nodes.new('ShaderNodeBsdfTransparent')
            transp.location = (250, 100)
            emis = nodes.new('ShaderNodeEmission')
            emis.location = (250, -100)

            if tex_img:
                mix_col = nodes.new('ShaderNodeMix')
                mix_col.data_type = 'RGBA'
                mix_col.blend_type = 'MULTIPLY'
                mix_col.location = (50, 0)
                mix_col.inputs[0].default_value = 1.0
                links.new(ramp.outputs['Color'], mix_col.inputs[6])
                links.new(tex_node.outputs['Color'], mix_col.inputs[7])
                links.new(mix_col.outputs[2], emis.inputs['Color'])

                mul_a = nodes.new('ShaderNodeMath')
                mul_a.operation = 'MULTIPLY'
                mul_a.location = (50, -200)
                links.new(ramp.outputs['Alpha'], mul_a.inputs[0])
                links.new(tex_node.outputs['Alpha'], mul_a.inputs[1])

                scale_emis = nodes.new('ShaderNodeMath')
                scale_emis.operation = 'MULTIPLY'
                scale_emis.inputs[1].default_value = 2.5
                scale_emis.location = (200, -200)
                links.new(mul_a.outputs['Value'], scale_emis.inputs[0])
                links.new(scale_emis.outputs['Value'], emis.inputs['Strength'])
            else:
                links.new(ramp.outputs['Color'], emis.inputs['Color'])
                emis.inputs['Strength'].default_value = a1 * 2.5

            links.new(transp.outputs['BSDF'], add_shader.inputs[0])
            links.new(emis.outputs['Emission'], add_shader.inputs[1])
            links.new(add_shader.outputs['Shader'], out_node.inputs['Surface'])
        else:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (300, 0)
            if 'Roughness' in bsdf.inputs:
                bsdf.inputs['Roughness'].default_value = 0.5
            if tex_img:
                mix_col = nodes.new('ShaderNodeMix')
                mix_col.data_type = 'RGBA'
                mix_col.blend_type = 'MULTIPLY'
                mix_col.location = (50, 0)
                mix_col.inputs[0].default_value = 1.0
                links.new(ramp.outputs['Color'], mix_col.inputs[6])
                links.new(tex_node.outputs['Color'], mix_col.inputs[7])
                links.new(mix_col.outputs[2], bsdf.inputs['Base Color'])
                links.new(mix_col.outputs[2], bsdf.inputs['Emission Color'])
                bsdf.inputs['Emission Strength'].default_value = 1.0

                mul_a = nodes.new('ShaderNodeMath')
                mul_a.operation = 'MULTIPLY'
                mul_a.location = (50, -200)
                links.new(ramp.outputs['Alpha'], mul_a.inputs[0])
                links.new(tex_node.outputs['Alpha'], mul_a.inputs[1])
                links.new(mul_a.outputs['Value'], bsdf.inputs['Alpha'])
            else:
                links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
                links.new(ramp.outputs['Alpha'], bsdf.inputs['Alpha'])
            links.new(bsdf.outputs['BSDF'], out_node.inputs['Surface'])

        bb_mesh.materials.append(mat)

        em_mesh = bpy.data.meshes.new(f"W3_Em_{emitter_name}_{emitter_idx}")
        em_mesh.from_pydata([(0.0, 0.0, 0.0)], (), ())
        emitter_obj = bpy.data.objects.new(f"W3_Emitter_{emitter_name}_{emitter_idx}", em_mesh)
        part_col.objects.link(emitter_obj)
        emitter_obj.parent = armatureObject
        emitter_obj.parent_type = 'BONE'
        emitter_obj.parent_bone = bone_name
        emitter_obj.location = (0.0, 0.0, 0.0)
        emitter_obj.rotation_euler = (0.0, 0.0, 0.0)

        emitter_meta = {
            'wc3_type': 'emitter',
            'wc3_emitter_name': emitter_name,
            'wc3_bone': bone_name,
            'wc3_speed': float(emitter.speed * s),
            'wc3_variation': float(emitter.variation),
            'wc3_cone_angle': float(getattr(emitter, 'cone_angle', 0.0)),
            'wc3_gravity': float(getattr(emitter, 'gravity', 0.0) * s),
            'wc3_life_span': float(emitter.life_span),
            'wc3_emission_rate': float(emitter.emission_rate),
            'wc3_width': float(emitter.width * s),
            'wc3_length': float(emitter.length * s),
            'wc3_filter_mode': int(emitter.filter_mode),
            'wc3_rows': int(emitter.rows),
            'wc3_columns': int(emitter.columns),
            'wc3_colors': [[float(x) for x in c] for c in emitter.segment_colors],
            'wc3_alphas': [float(a / 255.0) for a in emitter.segment_alphas],
            'wc3_time_middle': float(getattr(emitter, 'time_middle', 0.5)),
        }
        if tex_img:
            emitter_meta['wc3_texture'] = tex_img.name

        for k, v in emitter_meta.items():
            emitter_obj[k] = v

        if bone_name in armatureObject.data.bones:
            b_data = armatureObject.data.bones[bone_name]
            for k, v in emitter_meta.items():
                b_data[k] = v

        try:
            ps_mod = emitter_obj.modifiers.new(name="W3_Particles", type='PARTICLE_SYSTEM')
            ps_set = ps_mod.particle_system.settings
            ps_set.type = 'EMITTER'
            ps_set.physics_type = 'NEWTON'
            ps_set.count = int(min(max(emitter.emission_rate * 2.0, 15), 80))
            ps_set.lifetime = int(min(max(emitter.life_span * 30.0, 8), 45))
            ps_set.normal_factor = max(emitter.speed * s * 0.4, 0.15)
            ps_set.factor_random = min(max(emitter.variation, 0.1), 0.6)
            ps_set.effector_weights.gravity = 0.0
            ps_set.render_type = 'OBJECT'
            ps_set.instance_object = bb_obj
            ps_set.particle_size = 1.0
            ps_set.size_random = 0.3
            ps_set.display_size = 0.05
        except Exception as e:
            print(f"[WarCraft 3] Error configuring particle system: {e}")

        created_systems.append(emitter_obj)

    return created_systems


def create_warcraft3_material(material, material_index, bpyImages, model=None, team_color_rgb=(1.0, 0.0, 0.0)):
    layers = material.layers
    if not layers:
        mat = bpy.data.materials.new(name=f"Material_{material_index}")
        mat.use_nodes = True
        return mat

    layer0 = layers[0]
    tex0 = bpyImages[layer0.texture_id] if layer0.texture_id < len(bpyImages) else None

    effective_layer0 = layer0
    if (
        len(layers) >= 2
        and model is not None
        and 0 <= layer0.texture_id < len(model.textures)
        and model.textures[layer0.texture_id].replaceable_id == 1
        and layer0.filter_mode == 0
    ):
        layer1 = layers[1]
        tex1 = bpyImages[layer1.texture_id] if layer1.texture_id < len(bpyImages) else None
        if tex1 and layer1.filter_mode in (1, 2):
            comp_name = f"{tex1.name}_TeamColor"
            tex0 = composite_team_color_over_texture(team_color_rgb, tex1, comp_name)
            effective_layer0 = layer1

    mat_name = tex0.name if tex0 else f"Material_{material_index}"

    bpyMaterial = bpy.data.materials.new(name=mat_name)
    bpyMaterial.use_nodes = True
    nodes = bpyMaterial.node_tree.nodes
    links = bpyMaterial.node_tree.links
    nodes.clear()

    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (650, 0)

    obj_info = nodes.new('ShaderNodeObjectInfo')
    obj_info.location = (-650, 150)

    is_two_sided = bool(effective_layer0.shading_flags & 0x10)
    if is_two_sided:
        bpyMaterial.use_backface_culling = False
    else:
        bpyMaterial.use_backface_culling = True

    primary_mode = layer0.filter_mode
    is_unshaded = bool(effective_layer0.shading_flags & 0x1)

    bpyMaterial['wc3_filter_mode'] = int(primary_mode)
    bpyMaterial['wc3_blend'] = FILTER_MODE_NAMES.get(primary_mode, 'none')
    bpyMaterial['wc3_unshaded'] = bool(is_unshaded or primary_mode in (3, 4))
    bpyMaterial['wc3_two_sided'] = bool(is_two_sided)
    bpyMaterial['wc3_layer_alpha'] = float(effective_layer0.alpha)
    bpyMaterial['wc3_coord_id'] = int(effective_layer0.coord_id)
    bpyMaterial['wc3_mat_index'] = int(material_index)

    sec_layers_info = []
    self_illum_alpha = 0.0
    start_sec_idx = 2 if (effective_layer0 is not layer0) else 1
    for l_idx, l_obj in enumerate(layers[start_sec_idx:], start=start_sec_idx):
        l_tex = bpyImages[l_obj.texture_id] if (0 <= l_obj.texture_id < len(bpyImages)) else None
        if l_tex:
            is_same = bool(l_obj.texture_id == effective_layer0.texture_id)
            if is_same and (l_obj.filter_mode in (3, 4) or (l_obj.shading_flags & 0x1)):
                self_illum_alpha = max(self_illum_alpha, float(l_obj.alpha))
            sec_layers_info.append({
                'layer_index': int(l_idx),
                'tex_name': l_tex.name,
                'texture_id': int(l_obj.texture_id),
                'same_as_base': is_same,
                'filter_mode': int(l_obj.filter_mode),
                'alpha': float(l_obj.alpha),
                'two_sided': bool(l_obj.shading_flags & 0x10),
                'unshaded': bool(l_obj.shading_flags & 0x1),
            })
    bpyMaterial['wc3_sec_layers'] = sec_layers_info
    bpyMaterial['wc3_self_illum'] = float(self_illum_alpha)

    # CASE 1: Standalone Additive / AddAlpha Material (FilterMode 3 or 4)
    if primary_mode in (3, 4):
        bpyMaterial.use_backface_culling = False
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'BLEND'
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'BLENDED'
        if hasattr(bpyMaterial, 'show_transparent_back'):
            bpyMaterial.show_transparent_back = True
        if hasattr(bpyMaterial, 'use_transparency_overlap'):
            bpyMaterial.use_transparency_overlap = True

        add_shader = nodes.new('ShaderNodeAddShader')
        add_shader.location = (400, 0)

        transp_bsdf = nodes.new('ShaderNodeBsdfTransparent')
        transp_bsdf.location = (150, 100)
        transp_bsdf.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)

        emis_node = nodes.new('ShaderNodeEmission')
        emis_node.location = (150, -100)

        if tex0:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = tex0
            tex_node.location = (-350, 0)

            if layer0.texture_animation_id is not None and model and layer0.texture_animation_id < len(model.texture_animations):
                coord_node = nodes.new('ShaderNodeTexCoord')
                coord_node.location = (-750, 0)
                map_node = nodes.new('ShaderNodeMapping')
                map_node.name = f"Mapping_Mat{material_index}_L0"
                map_node.location = (-550, 0)
                links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
                links.new(map_node.outputs['Vector'], tex_node.inputs['Vector'])

            mix_col = nodes.new('ShaderNodeMix')
            mix_col.data_type = 'RGBA'
            mix_col.blend_type = 'MULTIPLY'
            mix_col.location = (-100, -50)
            mix_col.inputs[0].default_value = 1.0
            links.new(obj_info.outputs['Color'], mix_col.inputs[6])
            links.new(tex_node.outputs['Color'], mix_col.inputs[7])
            links.new(mix_col.outputs[2], emis_node.inputs['Color'])

            math_a = nodes.new('ShaderNodeMath')
            math_a.operation = 'MULTIPLY'
            math_a.location = (-100, 150)
            links.new(tex_node.outputs['Alpha'], math_a.inputs[0])
            links.new(obj_info.outputs['Alpha'], math_a.inputs[1])

            if layer0.alpha < 0.999:
                math_layer_a = nodes.new('ShaderNodeMath')
                math_layer_a.operation = 'MULTIPLY'
                math_layer_a.location = (50, 150)
                links.new(math_a.outputs['Value'], math_layer_a.inputs[0])
                math_layer_a.inputs[1].default_value = layer0.alpha
                links.new(math_layer_a.outputs['Value'], emis_node.inputs['Strength'])
            else:
                links.new(math_a.outputs['Value'], emis_node.inputs['Strength'])
        else:
            links.new(obj_info.outputs['Color'], emis_node.inputs['Color'])
            links.new(obj_info.outputs['Alpha'], emis_node.inputs['Strength'])

        links.new(transp_bsdf.outputs['BSDF'], add_shader.inputs[0])
        links.new(emis_node.outputs['Emission'], add_shader.inputs[1])
        links.new(add_shader.outputs['Shader'], output_node.inputs['Surface'])
        return bpyMaterial

    # CASE 2: Modulate Material (FilterMode 5 or 6)
    elif primary_mode in (5, 6):
        bpyMaterial.use_backface_culling = False
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'BLEND'
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'BLENDED'

        transp_bsdf = nodes.new('ShaderNodeBsdfTransparent')
        transp_bsdf.location = (300, 0)

        if tex0:
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = tex0
            tex_node.location = (-350, 0)

            mix_col = nodes.new('ShaderNodeMix')
            mix_col.data_type = 'RGBA'
            mix_col.blend_type = 'MULTIPLY'
            mix_col.location = (-50, 0)
            mix_col.inputs[0].default_value = 1.0
            links.new(obj_info.outputs['Color'], mix_col.inputs[6])
            links.new(tex_node.outputs['Color'], mix_col.inputs[7])
            links.new(mix_col.outputs[2], transp_bsdf.inputs['Color'])
        else:
            links.new(obj_info.outputs['Color'], transp_bsdf.inputs['Color'])

        links.new(transp_bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        return bpyMaterial

    # CASE 3: Standard Surfaces (FilterMode 0: Opaque, 1: Transparent Cutoff, 2: Blend)
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (300, 0)

    if 'Roughness' in bsdf.inputs:
        bsdf.inputs['Roughness'].default_value = 0.8
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = 0.0
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.0

    if primary_mode == 1:
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'CLIP'
            if hasattr(bpyMaterial, 'alpha_threshold'):
                bpyMaterial.alpha_threshold = 0.75
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'DITHERED'
    elif primary_mode == 2:
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'BLEND'
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'BLENDED'
    else:
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'HASHED'
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'DITHERED'

    if tex0:
        tex_node_0 = nodes.new('ShaderNodeTexImage')
        tex_node_0.image = tex0
        tex_node_0.location = (-350, 100)

        if effective_layer0.texture_animation_id is not None and model and effective_layer0.texture_animation_id < len(model.texture_animations):
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-750, 100)
            map_node = nodes.new('ShaderNodeMapping')
            map_node.name = f"Mapping_Mat{material_index}_L0"
            map_node.location = (-550, 100)
            links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
            links.new(map_node.outputs['Vector'], tex_node_0.inputs['Vector'])

        mix_col = nodes.new('ShaderNodeMix')
        mix_col.data_type = 'RGBA'
        mix_col.blend_type = 'MULTIPLY'
        mix_col.location = (-50, 100)
        mix_col.inputs[0].default_value = 1.0
        links.new(obj_info.outputs['Color'], mix_col.inputs[6])
        links.new(tex_node_0.outputs['Color'], mix_col.inputs[7])
        links.new(mix_col.outputs[2], bsdf.inputs['Base Color'])

        if primary_mode == 0:
            links.new(obj_info.outputs['Alpha'], bsdf.inputs['Alpha'])
        else:
            math_alpha = nodes.new('ShaderNodeMath')
            math_alpha.operation = 'MULTIPLY'
            math_alpha.location = (-50, -150)
            links.new(tex_node_0.outputs['Alpha'], math_alpha.inputs[0])
            links.new(obj_info.outputs['Alpha'], math_alpha.inputs[1])

            if effective_layer0.alpha < 0.999:
                math_layer_a = nodes.new('ShaderNodeMath')
                math_layer_a.operation = 'MULTIPLY'
                math_layer_a.location = (100, -150)
                links.new(math_alpha.outputs['Value'], math_layer_a.inputs[0])
                math_layer_a.inputs[1].default_value = effective_layer0.alpha
                links.new(math_layer_a.outputs['Value'], bsdf.inputs['Alpha'])
            else:
                links.new(math_alpha.outputs['Value'], bsdf.inputs['Alpha'])

        if effective_layer0.shading_flags & 0x1:
            links.new(mix_col.outputs[2], bsdf.inputs['Emission Color'])
            bsdf.inputs['Emission Strength'].default_value = 1.0

    curr_surface_output = bsdf.outputs['BSDF']

    for layer_idx, layer in enumerate(layers[start_sec_idx:], start=start_sec_idx):
        tex = bpyImages[layer.texture_id] if layer.texture_id < len(bpyImages) else None
        if not tex:
            continue

        loc_y = -350 - 250 * (layer_idx - 1)
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = tex
        tex_node.location = (-350, loc_y)

        if layer.texture_animation_id is not None and model and layer.texture_animation_id < len(model.texture_animations):
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-750, loc_y)
            map_node = nodes.new('ShaderNodeMapping')
            map_node.name = f"Mapping_Mat{material_index}_L{layer_idx}"
            map_node.location = (-550, loc_y)
            links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
            links.new(map_node.outputs['Vector'], tex_node.inputs['Vector'])

        if layer.filter_mode in (3, 4) or (layer.shading_flags & 0x1):
            add_shader = nodes.new('ShaderNodeAddShader')
            add_shader.location = (550 + 150 * (layer_idx - 1), 0)

            sec_emis_node = nodes.new('ShaderNodeEmission')
            sec_emis_node.location = (350, loc_y)

            mix_c = nodes.new('ShaderNodeMix')
            mix_c.data_type = 'RGBA'
            mix_c.blend_type = 'MULTIPLY'
            mix_c.location = (-100, loc_y)
            mix_c.inputs[0].default_value = 1.0
            links.new(obj_info.outputs['Color'], mix_c.inputs[6])
            links.new(tex_node.outputs['Color'], mix_c.inputs[7])
            links.new(mix_c.outputs[2], sec_emis_node.inputs['Color'])

            math_a = nodes.new('ShaderNodeMath')
            math_a.operation = 'MULTIPLY'
            math_a.location = (150, loc_y)
            links.new(tex_node.outputs['Alpha'], math_a.inputs[0])
            links.new(obj_info.outputs['Alpha'], math_a.inputs[1])

            scale_a = nodes.new('ShaderNodeMath')
            scale_a.operation = 'MULTIPLY'
            scale_a.location = (250, loc_y)
            links.new(math_a.outputs['Value'], scale_a.inputs[0])
            scale_a.inputs[1].default_value = layer.alpha
            links.new(scale_a.outputs['Value'], sec_emis_node.inputs['Strength'])

            links.new(curr_surface_output, add_shader.inputs[0])
            links.new(sec_emis_node.outputs['Emission'], add_shader.inputs[1])
            curr_surface_output = add_shader.outputs['Shader']

    links.new(curr_surface_output, output_node.inputs['Surface'])
    return bpyMaterial


def create_mesh_objects(model, importProperties):
    setTeamColor = getattr(importProperties, 'set_team_color', 'RED')
    team_color_rgb = constants.TEAM_COLORS.get(setTeamColor, (1.0, 0.0, 0.0))
    mdx_path = getattr(importProperties, 'mdx_file_path', '')

    model.normalize_meshes_names()
    bpyImages = []

    REPLACEABLE_TEXTURE_PATHS = {
        1: 'ReplaceableTextures\\TeamColor\\TeamColor00.blp',
        2: 'ReplaceableTextures\\TeamGlow\\TeamGlow00.blp',
        11: 'ReplaceableTextures\\Cliff\\Cliff0.blp',
        21: '',
        31: 'ReplaceableTextures\\LordaeronTree\\LordaeronSummerTree.blp',
        32: 'ReplaceableTextures\\AshenvaleTree\\AshenTree.blp',
        33: 'ReplaceableTextures\\BarrensTree\\BarrensTree.blp',
        34: 'ReplaceableTextures\\NorthrendTree\\NorthTree.blp',
        35: 'ReplaceableTextures\\Mushroom\\MushroomTree.blp',
        36: 'ReplaceableTextures\\RuinsTree\\RuinsTree.blp',
        37: 'ReplaceableTextures\\OutlandMushroomTree\\MushroomTree.blp',
    }

    for texture in model.textures:
        is_team_color = (texture.replaceable_id == 1)
        is_team_glow = (texture.replaceable_id == 2)

        if is_team_color:
            imageFile = constants.TEAM_COLOR_IMAGES.get(setTeamColor, '')
            tex_stem = f"TeamColor_{setTeamColor}"
        elif is_team_glow:
            imageFile = constants.TEAM_GLOW_IMAGES.get(setTeamColor, '')
            tex_stem = f"TeamGlow_{setTeamColor}"
        elif texture.replaceable_id in REPLACEABLE_TEXTURE_PATHS and REPLACEABLE_TEXTURE_PATHS[texture.replaceable_id]:
            imageFile = REPLACEABLE_TEXTURE_PATHS[texture.replaceable_id]
            tex_stem = os.path.splitext(os.path.basename(imageFile))[0]
        else:
            imageFile = texture.image_file_name or ''
            tex_stem = os.path.splitext(os.path.basename(imageFile))[0] if imageFile else "Texture"

        found_path = find_texture_file(imageFile, mdx_path, importProperties)
        bpyImage = None

        if found_path:
            bpyImage = load_or_convert_texture(found_path, tex_stem)

        if not bpyImage:
            if is_team_color:
                bpyImage = create_solid_color_image(tex_stem, (team_color_rgb[0], team_color_rgb[1], team_color_rgb[2], 1.0))
            elif is_team_glow:
                bpyImage = create_solid_color_image(tex_stem, (team_color_rgb[0], team_color_rgb[1], team_color_rgb[2], 0.75))
            else:
                bpyImage = create_solid_color_image(f"{tex_stem}_placeholder", (0.5, 0.5, 0.5, 1.0), 32, 32)

        bpyImages.append(bpyImage)

    bpyMaterials = []
    for mat_idx, material in enumerate(model.materials):
        bpyMaterial = create_warcraft3_material(material, mat_idx, bpyImages, model, team_color_rgb=team_color_rgb)
        bpyMaterials.append(bpyMaterial)

    model.bpy_images = bpyImages
    model.bpy_materials = bpyMaterials

    bpyObjects = []
    for mesh_idx, warCraft3Mesh in enumerate(model.meshes):
        bpyMesh = bpy.data.meshes.new(warCraft3Mesh.name)
        bpyObject = bpy.data.objects.new(warCraft3Mesh.name, bpyMesh)
        bpy.context.collection.objects.link(bpyObject)
        bpyMesh.from_pydata(warCraft3Mesh.vertices, (), warCraft3Mesh.triangles)

        for poly in bpyMesh.polygons:
            poly.use_smooth = True

        if hasattr(warCraft3Mesh, 'normals') and warCraft3Mesh.normals and len(warCraft3Mesh.normals) == len(warCraft3Mesh.vertices) and len(bpyMesh.polygons) > 0:
            try:
                safeNormals = [
                    (0.0, 0.0, 1.0) if not (n[0] * n[0] + n[1] * n[1] + n[2] * n[2] > 1e-12) else n
                    for n in warCraft3Mesh.normals
                ]
                bpyMesh.validate()
                bpyMesh.normals_split_custom_set([safeNormals[loop.vertex_index] for loop in bpyMesh.loops])
            except Exception:
                pass

        bpyMesh.uv_layers.new()
        uvLayer = bpyMesh.uv_layers.active.data
        for tris in bpyMesh.polygons:
            for loopIndex in range(tris.loop_start, tris.loop_start + tris.loop_total):
                vertexIndex = bpyMesh.loops[loopIndex].vertex_index
                uvLayer[loopIndex].uv = (warCraft3Mesh.uvs[vertexIndex])

        if warCraft3Mesh.material_id is not None and warCraft3Mesh.material_id < len(bpyMaterials):
            bpyMaterial = bpyMaterials[warCraft3Mesh.material_id]
            bpyMesh.materials.append(bpyMaterial)

        ga = next((g for g in model.geoset_animations if g.geoset_id == mesh_idx), None)
        if ga:
            init_c = getattr(ga, 'color', (1.0, 1.0, 1.0))
            init_a = getattr(ga, 'alpha', 1.0)
            # In Warcraft 3 MDX, if KGAO has a static track at t=0 (like Geoset 17's KGAO t=0: alpha=0.3),
            # that track value overrides the header's default `ga.alpha = 1.0`!
            if ga.animation_alpha and ga.animation_alpha.tracks_count == 1 and ga.animation_alpha.times[0] == 0:
                init_a = float(ga.animation_alpha.values[0])
            bpyObject.color = (init_c[0], init_c[1], init_c[2], init_a)
            max_anim_a = init_a
            if ga.animation_alpha and ga.animation_alpha.values:
                max_anim_a = max(max(ga.animation_alpha.values), init_a)
            bpyObject['wc3_init_alpha'] = float(init_a)
            bpyObject['wc3_max_alpha'] = float(max_anim_a)
        else:
            bpyObject.color = (1.0, 1.0, 1.0, 1.0)
            bpyObject['wc3_init_alpha'] = 1.0
            bpyObject['wc3_max_alpha'] = 1.0

        bpyObject['wc3_geoset_id'] = int(mesh_idx)
        bpyObject['wc3_selection_flags'] = int(getattr(warCraft3Mesh, 'selection_flags', 0))
        bpyObject['wc3_is_outline_shell'] = bool(is_inverted_outline_shell(model, mesh_idx))
        bpyObject['wc3_is_halo_cloud'] = bool(is_stacked_additive_halo_cloud(model, mesh_idx))

        for vertexGroupId in warCraft3Mesh.vertex_groups_ids:
            bpyObject.vertex_groups.new(name=str(vertexGroupId))

        for vertexIndex, vertexGroupIds in enumerate(warCraft3Mesh.vertex_groups):
            if not vertexGroupIds:
                continue
            weight = 1.0 / len(vertexGroupIds)
            for vertexGroupId in vertexGroupIds:
                bpyObject.vertex_groups[str(vertexGroupId)].add([vertexIndex, ], weight, 'REPLACE')

        bpyObjects.append(bpyObject)

    return bpyObjects


def create_armature_object(model, bpyObjects, boneSize):
    model.nodes.sort(key=lambda n: n.node.id if hasattr(n, 'node') and hasattr(n.node, 'id') and n.node.id is not None else 0)
    nodes = model.nodes
    pivotPoints = model.pivot_points
    bpyArmature = bpy.data.armatures.new(model.name + ' Nodes')
    bpyArmature.display_type = 'STICK'
    bpyObject = bpy.data.objects.new(model.name + ' Nodes', bpyArmature)
    bpyObject.show_in_front = True
    bpy.context.collection.objects.link(bpyObject)
    bpy.context.view_layer.objects.active = bpyObject
    bpy.ops.object.mode_set(mode='EDIT')

    nodeTypes = set()
    boneTypes = {}
    bone_names = []
    bonesByObjectId = {}

    for indexNode, node in enumerate(nodes):
        # PIVT and the parent field are Warcraft objectIds, which need not be contiguous.
        nodeId = node.node.id
        nodePosition = pivotPoints[nodeId] if nodeId is not None and nodeId < len(pivotPoints) else (0.0, 0.0, 0.0)
        boneName = node.node.name or f"Node_{indexNode}"
        nodeTypes.add(node.type)
        bone = bpyArmature.edit_bones.new(boneName)
        bone.head = nodePosition
        bone.tail = nodePosition
        bone.tail[1] += boneSize
        bone_names.append(bone.name)
        bonesByObjectId[nodeId] = bone.name
        boneTypes[bone.name] = node.type

    nodeTypes = list(nodeTypes)
    nodeTypes.sort()

    for indexNode, node in enumerate(nodes):
        parentBoneName = bonesByObjectId.get(node.node.parent)
        if parentBoneName is not None and parentBoneName != bone_names[indexNode]:
            bpyObject.data.edit_bones[indexNode].parent = bpyObject.data.edit_bones[parentBoneName]

    for mesh in bpyObjects:
        mesh.modifiers.new(name='Armature', type='ARMATURE')
        mesh.modifiers['Armature'].object = bpyObject
        for vertexGroup in mesh.vertex_groups:
            try:
                boneName = bonesByObjectId.get(int(vertexGroup.name))
            except ValueError:
                continue
            if boneName:
                vertexGroup.name = boneName

    bpy.ops.object.mode_set(mode='POSE')

    for nodeType in nodeTypes:
        collection_name = nodeType + 's'
        bone_collection = bpyObject.data.collections.get(collection_name)
        if not bone_collection:
            bone_collection = bpyObject.data.collections.new(collection_name)

    for bone in bpyObject.pose.bones:
        bone.rotation_mode = 'XYZ'
        node_type = boneTypes.get(bone.name, 'bone')
        collection_name = node_type + 's'
        bone_collection = bpyObject.data.collections.get(collection_name)
        if bone_collection:
            bone_collection.assign(bone.bone)

    for bone in bpyObject.data.bones:
        if hasattr(bone, 'warcraft_3'):
            bone.warcraft_3.nodeType = boneTypes.get(bone.name, 'BONE').upper()

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = None
    return bpyObject, bone_names


def add_sequence_to_armature(sequenceName, armatureObject, actionName=None):
    warcraft3data = armatureObject.data.warcraft_3
    sequence = warcraft3data.sequencesList.add()
    sequence.name = sequenceName
    sequence.action_name = actionName or sequenceName


def _iter_track_keyframes(track, intervalStart, intervalEnd, frameTime, global_sequences):
    """Yield (frame, value) pairs of a track within one animation sequence."""
    if track is None or not track.times:
        return
    gsid = getattr(track, 'global_sequence_id', None)
    isGlobal = gsid is not None and 0 <= gsid < len(global_sequences)
    seqLen = intervalEnd - intervalStart
    if isGlobal:
        period = global_sequences[gsid]
        if period <= 0:
            period = max(seqLen, 1)
        for index in range(track.tracks_count):
            time = track.times[index]
            value = track.values[index]
            t = time
            while t <= seqLen:
                if t >= 0:
                    yield (round(t / frameTime), value)
                t += period
        return
    for index in range(track.tracks_count):
        time = track.times[index]
        if intervalStart <= time and time <= intervalEnd:
            yield (round((time - intervalStart) / frameTime), track.values[index])


def _create_node_channel(action, datablock, dataPath, axisCount, keyframes, interpolationType):
    """Create one animated channel (XYZ axes) on an action."""
    if keyframes:
        fcurves = [create_fcurve(action, datablock, dataPath, index=i) for i in range(axisCount)]
        for frame, value in keyframes:
            for i in range(axisCount):
                key = fcurves[i].keyframe_points.insert(float(frame), value[i] if i < len(value) else 0.0)
                key.interpolation = interpolationType
        return True
    return False


def create_armature_actions(armatureObject, model, frameTime, bone_names):
    nodes = model.nodes
    sequences = model.sequences
    global_sequences = model.global_sequences

    def new_action(name, sequence_name):
        old_act = bpy.data.actions.get(name)
        if old_act and old_act.users == 0:
            try:
                bpy.data.actions.remove(old_act)
            except Exception:
                pass
        action = bpy.data.actions.new(name=name)
        action.use_fake_user = True
        action['wc3_armature_name'] = armatureObject.name
        action['wc3_sequence_name'] = sequence_name
        add_sequence_to_armature(sequence_name, armatureObject, action.name)
        return action

    action = new_action('#UNANIMATED', '#UNANIMATED')
    for indexNode, node in enumerate(nodes):
        if not (node.node.translations or node.node.rotations or node.node.scalings):
            continue
        boneName = bone_names[indexNode]
        dataPath = 'pose.bones["' + boneName + '"]'
        for i in range(3):
            fc = create_fcurve(action, armatureObject, dataPath + '.location', index=i)
            fc.keyframe_points.insert(0.0, 0.0)
        for i in range(3):
            fc = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=i)
            fc.keyframe_points.insert(0.0, 0.0)
        for i in range(3):
            fc = create_fcurve(action, armatureObject, dataPath + '.scale', index=i)
            fc.keyframe_points.insert(0.0, 1.0)

    for sequence in sequences:
        intervalStart = sequence.interval_start
        intervalEnd = sequence.interval_end
        seq_duration = intervalEnd - intervalStart
        max_frame = round(seq_duration / frameTime) if frameTime > 0 else 0.0
        action = new_action(sequence.name, sequence.name)
        for indexNode, node in enumerate(nodes):
            translations = node.node.translations
            rotations = node.node.rotations
            scalings = node.node.scalings
            if not (translations or rotations or scalings):
                continue
            boneName = bone_names[indexNode]
            dataPath = 'pose.bones["' + boneName + '"]'
            if translations:
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[translations.interpolation_type]
                keys = list(_iter_track_keyframes(translations, intervalStart, intervalEnd, frameTime, global_sequences))
                if keys:
                    keys.sort(key=lambda k: k[0])
                    if keys[0][0] > 0.0:
                        keys.insert(0, (0.0, keys[0][1]))
                    if keys[-1][0] < max_frame:
                        keys.append((max_frame, keys[-1][1]))
                if not _create_node_channel(action, armatureObject, dataPath + '.location', 3, keys, interpolationType):
                    for i in range(3):
                        fc = create_fcurve(action, armatureObject, dataPath + '.location', index=i)
                        fc.keyframe_points.insert(0.0, 0.0)
                        fc.keyframe_points.insert(float(max_frame), 0.0)
            if rotations:
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[rotations.interpolation_type]
                rotKeys = []
                prev_euler = None
                prev_q = None
                for frame, quat in _iter_track_keyframes(rotations, intervalStart, intervalEnd, frameTime, global_sequences):
                    q = mathutils.Quaternion(quat)
                    # Quaternion sign continuity: prevent 360-degree flips
                    if prev_q is not None and q.dot(prev_q) < 0.0:
                        q.negate()
                    prev_q = q.copy()
                    euler = q.to_euler('XYZ')
                    # Euler continuity: prevent gimbal lock / wrapping jumps
                    if prev_euler is not None:
                        euler.make_compatible(prev_euler)
                    prev_euler = euler.copy()
                    rotKeys.append((frame, (euler[0], euler[1], euler[2])))
                if rotKeys:
                    rotKeys.sort(key=lambda k: k[0])
                    if rotKeys[0][0] > 0.0:
                        rotKeys.insert(0, (0.0, rotKeys[0][1]))
                    if rotKeys[-1][0] < max_frame:
                        rotKeys.append((max_frame, rotKeys[-1][1]))
                if not _create_node_channel(action, armatureObject, dataPath + '.rotation_euler', 3, rotKeys, interpolationType):
                    for i in range(3):
                        fc = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=i)
                        fc.keyframe_points.insert(0.0, 0.0)
                        fc.keyframe_points.insert(float(max_frame), 0.0)
            if scalings:
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[scalings.interpolation_type]
                keys = list(_iter_track_keyframes(scalings, intervalStart, intervalEnd, frameTime, global_sequences))
                if keys:
                    keys.sort(key=lambda k: k[0])
                    if keys[0][0] > 0.0:
                        keys.insert(0, (0.0, keys[0][1]))
                    if keys[-1][0] < max_frame:
                        keys.append((max_frame, keys[-1][1]))
                if not _create_node_channel(action, armatureObject, dataPath + '.scale', 3, keys, interpolationType):
                    for i in range(3):
                        fc = create_fcurve(action, armatureObject, dataPath + '.scale', index=i)
                        fc.keyframe_points.insert(0.0, 1.0)
                        fc.keyframe_points.insert(float(max_frame), 1.0)


CAMERA_SENSOR_WIDTH_DEFAULT = 36.0


def fov_to_lens(fovRadians):
    if fovRadians <= 0.001:
        fovRadians = 0.001
    return CAMERA_SENSOR_WIDTH_DEFAULT / (2.0 * math.tan(fovRadians / 2.0))


def _new_tagged_action(name, sequenceName, armatureName, objectName=None, channel='object'):
    old_act = bpy.data.actions.get(name)
    if old_act and old_act.users == 0:
        try:
            bpy.data.actions.remove(old_act)
        except Exception:
            pass
    action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    action['wc3_armature_name'] = armatureName
    action['wc3_sequence_name'] = sequenceName
    if objectName:
        action['wc3_object_name'] = objectName
    action['wc3_channel'] = channel
    return action


def _write_tracked_channel(track, datablock, staticValue, armatureName, objectName, baseName, channel, sequences, frameTime, global_sequences, scalarFn=None):
    """Create one action per animation sequence for a vec3 or scalar track."""
    if not sequences:
        return None
    value0 = scalarFn(staticValue) if scalarFn else tuple(staticValue)
    axisCount = len(value0)

    action = _new_tagged_action('#UNANIMATED ' + baseName, '#UNANIMATED', armatureName, objectName, channel)
    for i in range(axisCount):
        fc = create_fcurve(action, datablock, channel, index=i)
        fc.keyframe_points.insert(0.0, value0[i])
    unanimated = action

    for sequence in sequences:
        intervalStart = sequence.interval_start
        intervalEnd = sequence.interval_end
        action = _new_tagged_action(sequence.name + ' ' + baseName, sequence.name, armatureName, objectName, channel)
        keys = []
        interpolationType = 'LINEAR'
        if track is not None and track.times:
            interpolationType = constants.INTERPOLATION_TYPE_NAMES.get(track.interpolation_type, 'LINEAR')
            for frame, value in _iter_track_keyframes(track, intervalStart, intervalEnd, frameTime, global_sequences):
                keys.append((frame, scalarFn(value) if scalarFn else value))
        if not keys:
            keys = [(0, value0)]
        fcurves = [create_fcurve(action, datablock, channel, index=i) for i in range(axisCount)]
        for frame, value in keys:
            for i in range(axisCount):
                key = fcurves[i].keyframe_points.insert(float(frame), value[i] if i < len(value) else 0.0)
                key.interpolation = interpolationType
    return unanimated


def create_cameras(model, armatureObject, frameTime):
    """Import CAMS entries as Blender cameras with an animated target empty."""
    arm_scale = armatureObject.scale[0] if armatureObject.scale and armatureObject.scale[0] else 0.03
    for camera in model.cameras:
        baseName = camera.name or 'Camera'
        cam_data = bpy.data.cameras.new(baseName)
        cam_obj = bpy.data.objects.new(baseName, cam_data)
        cam_obj.parent = armatureObject
        cam_obj.location = camera.position
        cam_data.lens = fov_to_lens(camera.field_of_view)
        cam_data.clip_start = max(camera.near_clipping_plane * arm_scale, 0.001)
        cam_data.clip_end = max(camera.far_clipping_plane * arm_scale, 0.1)
        bpy.context.collection.objects.link(cam_obj)

        targetName = baseName + ' Target'
        target_obj = bpy.data.objects.new(targetName, None)
        target_obj.empty_display_type = 'PLAIN_AXES'
        target_obj.parent = armatureObject
        target_obj.location = camera.target_position
        bpy.context.collection.objects.link(target_obj)

        constraint = cam_obj.constraints.new(type='TRACK_TO')
        constraint.target = target_obj
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis = 'UP_Y'

        obj_act = _write_tracked_channel(camera.translations, cam_obj, camera.position,
                                         armatureObject.name, cam_obj.name, cam_obj.name, 'location',
                                         model.sequences, frameTime, model.global_sequences)
        if obj_act:
            cam_obj.animation_data.action = obj_act
        tgt_act = _write_tracked_channel(camera.target_translations, target_obj, camera.target_position,
                                         armatureObject.name, target_obj.name, target_obj.name, 'location',
                                         model.sequences, frameTime, model.global_sequences)
        if tgt_act:
            target_obj.animation_data.action = tgt_act
        lens_act = _write_tracked_channel(camera.fov_track, cam_data, (camera.field_of_view,),
                                          armatureObject.name, cam_obj.name, cam_obj.name + ' (fov)', 'lens',
                                          model.sequences, frameTime, model.global_sequences,
                                          scalarFn=lambda v: (fov_to_lens(v if isinstance(v, float) else v[0]),))
        if lens_act:
            cam_data.animation_data.action = lens_act


def _light_sequence_actions(light, light_data, armatureName, sequences, frameTime, global_sequences):
    """One action per sequence carrying both 'energy' and 'color' channels."""
    def staticEnergy():
        return (max(light.intensity, 0.0) * 1000.0,)
    staticColor = tuple(light.color)
    energyFn = lambda v: (max(v, 0.0) * 1000.0,)

    unanimated = _new_tagged_action('#UNANIMATED ' + light_data.name + ' (light)', '#UNANIMATED', armatureName, light_data.name, 'light')
    for i in range(1):
        fc = create_fcurve(unanimated, light_data, 'energy', index=i)
        fc.keyframe_points.insert(0.0, staticEnergy()[i])
    for i in range(3):
        fc = create_fcurve(unanimated, light_data, 'color', index=i)
        fc.keyframe_points.insert(0.0, staticColor[i])

    for sequence in sequences:
        intervalStart = sequence.interval_start
        intervalEnd = sequence.interval_end
        action = _new_tagged_action(sequence.name + ' ' + light_data.name + ' (light)', sequence.name, armatureName, light_data.name, 'light')
        energyKeys = []
        energyInterp = 'LINEAR'
        if light.intensity_track is not None and light.intensity_track.times:
            energyInterp = constants.INTERPOLATION_TYPE_NAMES.get(light.intensity_track.interpolation_type, 'LINEAR')
            for frame, value in _iter_track_keyframes(light.intensity_track, intervalStart, intervalEnd, frameTime, global_sequences):
                energyKeys.append((frame, energyFn(value)))
        if not energyKeys:
            energyKeys = [(0, staticEnergy())]
        colorKeys = []
        colorInterp = 'LINEAR'
        if light.color_track is not None and light.color_track.times:
            colorInterp = constants.INTERPOLATION_TYPE_NAMES.get(light.color_track.interpolation_type, 'LINEAR')
            colorKeys = list(_iter_track_keyframes(light.color_track, intervalStart, intervalEnd, frameTime, global_sequences))
        if not colorKeys:
            colorKeys = [(0, staticColor)]
        fcE = create_fcurve(action, light_data, 'energy', index=0)
        for frame, value in energyKeys:
            key = fcE.keyframe_points.insert(float(frame), value[0])
            key.interpolation = energyInterp
        fcC = [create_fcurve(action, light_data, 'color', index=i) for i in range(3)]
        for frame, value in colorKeys:
            for i in range(3):
                key = fcC[i].keyframe_points.insert(float(frame), value[i] if i < len(value) else 0.0)
                key.interpolation = colorInterp
    return unanimated


def create_lights(model, armatureObject, bone_names, frameTime):
    """Import LITE entries as Blender lights parented into the node hierarchy."""
    arm_scale = armatureObject.scale[0] if armatureObject.scale and armatureObject.scale[0] else 0.03
    bonesByObjectId = {node.node.id: bone_names[index] for index, node in enumerate(model.nodes)}
    for light in model.lights:
        baseName = (light.node.name if light.node and light.node.name else 'Light')
        light_data = bpy.data.lights.new(baseName, 'POINT')
        if light.light_type == 1:
            light_data.type = 'SUN'
        light_data.color = light.color
        light_data.energy = max(light.intensity, 0.0) * 1000.0
        if light.attenuation[1] > 0 and hasattr(light_data, 'custom_distance'):
            try:
                light_data.use_custom_distance = True
                light_data.custom_distance = max(light.attenuation[1] * arm_scale, 0.01)
            except Exception:
                pass
        light_obj = bpy.data.objects.new(baseName, light_data)
        parentId = light.node.parent if light.node else None
        parentBoneName = bonesByObjectId.get(parentId)
        if parentBoneName is not None:
            light_obj.parent = armatureObject
            light_obj.parent_type = 'BONE'
            light_obj.parent_bone = parentBoneName
            light_obj.location = (0.0, 0.0, 0.0)
        else:
            light_obj.parent = armatureObject
            nodeId = light.node.id if light.node and light.node.id is not None else 0
            if 0 <= nodeId < len(model.pivot_points):
                light_obj.location = model.pivot_points[nodeId]
        bpy.context.collection.objects.link(light_obj)

        light_act = _light_sequence_actions(light, light_data, armatureObject.name,
                                            model.sequences, frameTime, model.global_sequences)
        if light_act:
            light_data.animation_data.action = light_act


def create_object_actions(model, bpyObjects, frameTime, armatureObject=None):
    geosetAnimations = model.geoset_animations
    sequences = model.sequences
    dataPathColor = 'color'
    arm_name = armatureObject.name if armatureObject else ""

    for geosetAnimation in geosetAnimations:
        geosetId = geosetAnimation.geoset_id
        if geosetId >= len(bpyObjects):
            continue
        obj = bpyObjects[geosetId]
        init_col = getattr(geosetAnimation, 'color', (1.0, 1.0, 1.0))
        init_alpha = getattr(geosetAnimation, 'alpha', 1.0)
        if geosetAnimation.animation_alpha and geosetAnimation.animation_alpha.tracks_count == 1 and geosetAnimation.animation_alpha.times[0] == 0:
            init_alpha = float(geosetAnimation.animation_alpha.values[0])

        act_name = '#UNANIMATED' + ' ' + obj.name
        old_act = bpy.data.actions.get(act_name)
        if old_act and old_act.users == 0:
            try:
                bpy.data.actions.remove(old_act)
            except Exception:
                pass

        action = bpy.data.actions.new(name=act_name)
        action.use_fake_user = True
        action['wc3_armature_name'] = arm_name
        action['wc3_object_name'] = obj.name
        action['wc3_sequence_name'] = '#UNANIMATED'
        colorR = create_fcurve(action, obj, dataPathColor, index=0)
        colorG = create_fcurve(action, obj, dataPathColor, index=1)
        colorB = create_fcurve(action, obj, dataPathColor, index=2)
        colorA = create_fcurve(action, obj, dataPathColor, index=3)
        colorR.keyframe_points.insert(0.0, init_col[0])
        colorG.keyframe_points.insert(0.0, init_col[1])
        colorB.keyframe_points.insert(0.0, init_col[2])
        colorA.keyframe_points.insert(0.0, init_alpha)

    for sequence in sequences:
        intervalStart = sequence.interval_start
        intervalEnd = sequence.interval_end
        for geosetAnimation in geosetAnimations:
            geosetId = geosetAnimation.geoset_id
            if geosetId >= len(bpyObjects):
                continue
            obj = bpyObjects[geosetId]
            init_col = getattr(geosetAnimation, 'color', (1.0, 1.0, 1.0))
            init_alpha = getattr(geosetAnimation, 'alpha', 1.0)
            if geosetAnimation.animation_alpha and geosetAnimation.animation_alpha.tracks_count == 1 and geosetAnimation.animation_alpha.times[0] == 0:
                init_alpha = float(geosetAnimation.animation_alpha.values[0])
            colorAnim = geosetAnimation.animation_color
            alphaAnim = geosetAnimation.animation_alpha

            act_name = sequence.name + ' ' + obj.name
            old_act = bpy.data.actions.get(act_name)
            if old_act and old_act.users == 0:
                try:
                    bpy.data.actions.remove(old_act)
                except Exception:
                    pass

            action = bpy.data.actions.new(name=act_name)
            action.use_fake_user = True
            action['wc3_armature_name'] = arm_name
            action['wc3_object_name'] = obj.name
            action['wc3_sequence_name'] = sequence.name
            colorR = None
            colorG = None
            colorB = None
            colorA = None
            interpolationType = constants.INTERPOLATION_TYPE_NAMES[colorAnim.interpolation_type]
            for index in range(colorAnim.tracks_count):
                time = colorAnim.times[index]
                color = colorAnim.values[index]
                if intervalStart <= time and time <= intervalEnd or time == 0:
                    if not colorR:
                        colorR = create_fcurve(action, obj, dataPathColor, index=0)
                    if not colorG:
                        colorG = create_fcurve(action, obj, dataPathColor, index=1)
                    if not colorB:
                        colorB = create_fcurve(action, obj, dataPathColor, index=2)
                    if time == 0:
                        realTime = 0.0
                    else:
                        realTime = round((time - intervalStart) / frameTime, 0)
                    colorRKeyframe = colorR.keyframe_points.insert(realTime, color[0])
                    colorGKeyframe = colorG.keyframe_points.insert(realTime, color[1])
                    colorBKeyframe = colorB.keyframe_points.insert(realTime, color[2])
                    colorRKeyframe.interpolation = interpolationType
                    colorGKeyframe.interpolation = interpolationType
                    colorBKeyframe.interpolation = interpolationType
            if not colorR:
                colorR = create_fcurve(action, obj, dataPathColor, index=0)
                colorR.keyframe_points.insert(0.0, init_col[0])
            if not colorG:
                colorG = create_fcurve(action, obj, dataPathColor, index=1)
                colorG.keyframe_points.insert(0.0, init_col[1])
            if not colorB:
                colorB = create_fcurve(action, obj, dataPathColor, index=2)
                colorB.keyframe_points.insert(0.0, init_col[2])

            interpolationType = constants.INTERPOLATION_TYPE_NAMES[alphaAnim.interpolation_type]
            for index in range(alphaAnim.tracks_count):
                time = alphaAnim.times[index]
                alpha = alphaAnim.values[index]
                if intervalStart <= time and time <= intervalEnd or time == 0:
                    if not colorA:
                        colorA = create_fcurve(action, obj, dataPathColor, index=3)
                    if time == 0:
                        realTime = 0.0
                    else:
                        realTime = round((time - intervalStart) / frameTime, 0)
                    colorAKeyframe = colorA.keyframe_points.insert(realTime, alpha)
                    colorAKeyframe.interpolation = interpolationType
            if not colorA:
                colorA = create_fcurve(action, obj, dataPathColor, index=3)
                colorA.keyframe_points.insert(0.0, init_alpha)


def load_warcraft_3_model(model, importProperties):
    purge_orphaned_wc3_actions()
    bpyObjects = create_mesh_objects(model, importProperties)
    armatureObject, bone_names = create_armature_object(model, bpyObjects, importProperties.bone_size)

    for obj in bpyObjects:
        obj.parent = armatureObject
        obj.matrix_parent_inverse.identity()
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)

    g_scale = getattr(importProperties, 'global_scale', 0.03)
    if getattr(importProperties, 'import_particles', True):
        bpyImages = getattr(model, 'bpy_images', [])
        create_particle_emitter_systems(model, armatureObject, bone_names, bpyImages, g_scale)

    WC3_EMITTERS_CACHE[armatureObject.name] = getattr(model, 'particle_emitters_2', [])
    armatureObject['wc3_global_scale'] = g_scale

    bpyMaterials = getattr(model, 'bpy_materials', [])
    animate_texture_animations(model, bpyMaterials, importProperties.frame_time)

    if hasattr(importProperties, 'global_scale'):
        s = importProperties.global_scale
        armatureObject.scale = (s, s, s)

    armatureObject.rotation_euler[2] = -math.radians(90.0)

    if model.cameras:
        try:
            create_cameras(model, armatureObject, importProperties.frame_time)
        except Exception as e:
            print('[WarCraft 3] Error importing cameras: {0}'.format(e))
    if model.lights:
        try:
            create_lights(model, armatureObject, bone_names, importProperties.frame_time)
        except Exception as e:
            print('[WarCraft 3] Error importing lights: {0}'.format(e))

    create_armature_actions(armatureObject, model, importProperties.frame_time, bone_names)
    create_object_actions(model, bpyObjects, importProperties.frame_time, armatureObject)

    target_action = None
    target_seq_name = None
    target_idx = 0
    if model.sequences:
        for idx, seq in enumerate(model.sequences):
            if seq.name and seq.name != '#UNANIMATED':
                act = bpy.data.actions.get(seq.name)
                if not act:
                    for a in bpy.data.actions:
                        if a.get('wc3_armature_name') == armatureObject.name and a.get('wc3_sequence_name') == seq.name:
                            act = a
                            break
                if act:
                    target_action = act
                    target_seq_name = seq.name
                    target_idx = idx + 1
                    break
    if not target_action:
        target_action = bpy.data.actions.get('#UNANIMATED')
        target_seq_name = '#UNANIMATED'
        target_idx = 0

    if target_action and armatureObject.animation_data:
        armatureObject.animation_data.action = target_action
        if hasattr(armatureObject.data, 'warcraft_3'):
            armatureObject.data.warcraft_3.sequencesListIndex = target_idx
        if hasattr(target_action, 'frame_range'):
            bpy.context.scene.frame_start = int(round(target_action.frame_range[0]))
            bpy.context.scene.frame_end = int(round(target_action.frame_range[1]))
            bpy.context.scene.frame_current = bpy.context.scene.frame_start

        if target_seq_name:
            for obj in bpyObjects:
                obj_act = bpy.data.actions.get(target_seq_name + ' ' + obj.name)
                if not obj_act:
                    for a in bpy.data.actions:
                        if a.get('wc3_object_name') == obj.name and a.get('wc3_sequence_name') == target_seq_name:
                            obj_act = a
                            break
                if obj_act:
                    if obj.animation_data is None:
                        obj.animation_data_create()
                    obj.animation_data.action = obj_act

    bpy.context.view_layer.objects.active = armatureObject
    armatureObject.select_set(True)
    return armatureObject
