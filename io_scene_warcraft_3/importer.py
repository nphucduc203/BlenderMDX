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
                        # Also index relative path from root
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
    
    # 1. Custom search dir from import dialog
    custom_dir = getattr(importProperties, 'texture_search_dir', '')
    if custom_dir and os.path.isdir(str(custom_dir)):
        search_roots.append(str(custom_dir))

    # 2. Local MDX folder and parent folders (e.g. Work/)
    if mdx_dir and os.path.isdir(mdx_dir):
        search_roots.append(mdx_dir)
    if parent_dir and os.path.isdir(parent_dir):
        search_roots.append(parent_dir)
    if grandparent_dir and os.path.isdir(grandparent_dir):
        search_roots.append(grandparent_dir)

    # 3. Preferences directories
    pref = get_preferences()
    if pref:
        for p_dir in [getattr(pref, 'resourceFolder', ''), getattr(pref, 'alternativeResourceFolder', '')]:
            p_dir_str = str(p_dir).strip()
            if p_dir_str and os.path.isdir(p_dir_str):
                search_roots.append(p_dir_str)

    # Fast direct check first
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

    # Use fast indexed search for recursive / case-insensitive matching
    tex_index = get_texture_index(search_roots)
    
    # Check exact clean name in index
    key_clean = clean_name.lower()
    if key_clean in tex_index:
        return tex_index[key_clean]

    # Check flat basename in index
    key_base = base_name.lower()
    if key_base in tex_index:
        return tex_index[key_base]

    # Check alternative extensions
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
            b_img.pack()
            return b_img
        except Exception as e:
            print(f"[WarCraft 3] Error converting BLP {found_path}: {e}")
            return None
    else:
        try:
            b_img = bpy.data.images.load(found_path)
            b_img.name = tex_name
            b_img.pack()
            return b_img
        except Exception as e:
            print(f"[WarCraft 3] Error loading image {found_path}: {e}")
            return None


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
    """Purge orphaned actions created by Warcraft 3 plugin that have no active object in the scene."""
    existing_armatures = {obj.name for obj in bpy.data.objects if obj.type == 'ARMATURE'}
    existing_meshes = {obj.name for obj in bpy.data.objects if obj.type == 'MESH'}
    for act in list(bpy.data.actions):
        arm_tag = act.get('wc3_armature_name', None)
        obj_tag = act.get('wc3_object_name', None)
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
    Convert Warcraft 3 ParticleEmitter2 into functional Blender particle systems:
    - Zero gravity (no falling snow/rain)
    - 3-segment color/alpha transitions (Start, Mid, End) via ColorRamp and Particle Info
    - Sprite sheet flipbook animations for multi-frame particles (e.g. fire, star)
    - Managed under a dedicated 'WarCraft 3 Particles' collection
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

    for emitter_idx, emitter in enumerate(model.particle_emitters_2):
        node_id = emitter.node.id if emitter.node else -1
        if node_id is None or node_id >= len(bone_names) or node_id < 0:
            continue
        bone_name = bone_names[node_id]
        emitter_name = emitter.node.name or f"Emitter_{emitter_idx}"

        # 1. Billboard instance quad placed offscreen
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
        bb_obj.location = (0.0, 0.0, -1000.0) # Hidden far off-screen
        inst_col.objects.link(bb_obj)

        # 2. Particle Material with ColorRamp and Flipbook
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

        # Shading: Additive vs Alpha Blend
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

        # 3. Create emitter object attached to parent bone
        em_mesh = bpy.data.meshes.new(f"W3_Em_{emitter_name}_{emitter_idx}")
        em_mesh.from_pydata([(0.0, 0.0, 0.0)], (), ())
        emitter_obj = bpy.data.objects.new(f"W3_Emitter_{emitter_name}_{emitter_idx}", em_mesh)
        part_col.objects.link(emitter_obj)
        emitter_obj.parent = armatureObject
        emitter_obj.parent_type = 'BONE'
        emitter_obj.parent_bone = bone_name
        emitter_obj.location = (0.0, 0.0, 0.0)
        emitter_obj.rotation_euler = (0.0, 0.0, 0.0)

        # 4. Attach and configure Particle System
        try:
            ps_mod = emitter_obj.modifiers.new(name="W3_Particles", type='PARTICLE_SYSTEM')
            ps_set = ps_mod.particle_system.settings
            ps_set.type = 'EMITTER'
            ps_set.physics_type = 'NEWTON'
            ps_set.count = int(min(max(emitter.emission_rate * 2.0, 15), 80))
            ps_set.lifetime = int(min(max(emitter.life_span * 30.0, 8), 45))
            ps_set.normal_factor = max(emitter.speed * s * 0.4, 0.15)
            ps_set.factor_random = min(max(emitter.variation, 0.1), 0.6)
            ps_set.effector_weights.gravity = 0.0 # ZERO gravity: float and swirl, NO RAIN/SNOW!
            ps_set.render_type = 'OBJECT'
            ps_set.instance_object = bb_obj
            ps_set.particle_size = 1.0
            ps_set.size_random = 0.3
            ps_set.display_size = 0.05
        except Exception as e:
            print(f"[WarCraft 3] Error configuring particle system: {e}")

        created_systems.append(emitter_obj)

    return created_systems


def load_warcraft_3_model(model, importProperties):
    purge_orphaned_wc3_actions()
    bpyObjects = create_mesh_objects(model, importProperties)
    armatureObject, bone_names = create_armature_object(model, bpyObjects, importProperties.bone_size)

    # Parent every mesh cleanly to the Armature object
    for obj in bpyObjects:
        obj.parent = armatureObject
        obj.matrix_parent_inverse.identity()
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)

    # Convert particle emitters if enabled
    g_scale = getattr(importProperties, 'global_scale', 0.03)
    if getattr(importProperties, 'import_particles', True):
        bpyImages = getattr(model, 'bpy_images', [])
        create_particle_emitter_systems(model, armatureObject, bone_names, bpyImages, g_scale)

    # Cache particle data on armature for operator conversion
    WC3_EMITTERS_CACHE[armatureObject.name] = getattr(model, 'particle_emitters_2', [])
    armatureObject['wc3_global_scale'] = g_scale


    # Animate texture animations on materials
    bpyMaterials = getattr(model, 'bpy_materials', [])
    animate_texture_animations(model, bpyMaterials, importProperties.frame_time)

    # Apply global scale and root rotation to the Armature (children meshes inherit it)
    if hasattr(importProperties, 'global_scale'):
        s = importProperties.global_scale
        armatureObject.scale = (s, s, s)
    
    armatureObject.rotation_euler[2] = -math.radians(90.0)

    create_armature_actions(armatureObject, model, importProperties.frame_time, bone_names)
    create_object_actions(model, bpyObjects, importProperties.frame_time, armatureObject)

    # Set initial active action to the first real sequence if available (e.g. Stand)
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
                    target_idx = idx + 1 # sequencesList has #UNANIMATED at index 0
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
        
        # Also assign corresponding mesh actions if any
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

    # Activate and select the armature so the user immediately sees the rig and its animations
    bpy.context.view_layer.objects.active = armatureObject
    armatureObject.select_set(True)
    return armatureObject


def create_warcraft3_material(material, material_index, bpyImages, model=None):
    layers = material.layers
    if not layers:
        mat = bpy.data.materials.new(name=f"Material_{material_index}")
        mat.use_nodes = True
        return mat

    layer0 = layers[0]
    tex0 = bpyImages[layer0.texture_id] if layer0.texture_id < len(bpyImages) else None
    mat_name = tex0.name if tex0 else f"Material_{material_index}"
    
    bpyMaterial = bpy.data.materials.new(name=mat_name)
    bpyMaterial.use_nodes = True
    nodes = bpyMaterial.node_tree.nodes
    links = bpyMaterial.node_tree.links
    nodes.clear()

    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (650, 0)

    # Object Info node for live geoset animation color tint and alpha
    obj_info = nodes.new('ShaderNodeObjectInfo')
    obj_info.location = (-650, 150)

    # Determine blend mode and two-sided flags
    is_two_sided = any(bool(l.shading_flags & 0x10) for l in layers)
    if is_two_sided:
        bpyMaterial.use_backface_culling = False
    else:
        bpyMaterial.use_backface_culling = True

    primary_mode = layer0.filter_mode

    # ---------------------------------------------------------
    # CASE 1: Standalone Additive / AddAlpha Material (FilterMode 3 or 4)
    # Magic glows, halos, missiles, particle cards, ribbons, aura planes
    # Uses Transparent BSDF + Emission Shader via Add Shader so black areas (0,0,0)
    # add 0 light (100% transparent), and glowing areas add radiant light.
    # ---------------------------------------------------------
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

            # Mix texture color with ObjectInfo.Color
            mix_col = nodes.new('ShaderNodeMix')
            mix_col.data_type = 'RGBA'
            mix_col.blend_type = 'MULTIPLY'
            mix_col.location = (-100, -50)
            mix_col.inputs[0].default_value = 1.0
            links.new(obj_info.outputs['Color'], mix_col.inputs[6])
            links.new(tex_node.outputs['Color'], mix_col.inputs[7])
            links.new(mix_col.outputs[2], emis_node.inputs['Color'])

            # Modulate emission strength by Texture Alpha, Object Alpha, and Layer Alpha
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

    # ---------------------------------------------------------
    # CASE 2: Modulate Material (FilterMode 5 or 6)
    # Multiplicative shadows, decals, projector textures
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # CASE 3: Standard Surfaces (FilterMode 0: Opaque, 1: Transparent Cutoff, 2: Blend)
    # Characters, units, buildings, armor, weapons
    # ---------------------------------------------------------
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (300, 0)
    
    # Retro fantasy look: matte roughness, non-metallic, zero specular sheen
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
        # primary_mode == 0 (Opaque)
        if hasattr(bpyMaterial, 'blend_method'):
            bpyMaterial.blend_method = 'HASHED'
        if hasattr(bpyMaterial, 'surface_render_method'):
            bpyMaterial.surface_render_method = 'DITHERED'

    if tex0:
        tex_node_0 = nodes.new('ShaderNodeTexImage')
        tex_node_0.image = tex0
        tex_node_0.location = (-350, 100)

        if layer0.texture_animation_id is not None and model and layer0.texture_animation_id < len(model.texture_animations):
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-750, 100)
            map_node = nodes.new('ShaderNodeMapping')
            map_node.name = f"Mapping_Mat{material_index}_L0"
            map_node.location = (-550, 100)
            links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
            links.new(map_node.outputs['Vector'], tex_node_0.inputs['Vector'])

        # Mix texture color with ObjectInfo.Color
        mix_col = nodes.new('ShaderNodeMix')
        mix_col.data_type = 'RGBA'
        mix_col.blend_type = 'MULTIPLY'
        mix_col.location = (-50, 100)
        mix_col.inputs[0].default_value = 1.0
        links.new(obj_info.outputs['Color'], mix_col.inputs[6])
        links.new(tex_node_0.outputs['Color'], mix_col.inputs[7])
        links.new(mix_col.outputs[2], bsdf.inputs['Base Color'])

        # Alpha connection
        if primary_mode == 0:
            # Opaque: only modulates by geoset alpha fade
            links.new(obj_info.outputs['Alpha'], bsdf.inputs['Alpha'])
        else:
            math_alpha = nodes.new('ShaderNodeMath')
            math_alpha.operation = 'MULTIPLY'
            math_alpha.location = (-50, -150)
            links.new(tex_node_0.outputs['Alpha'], math_alpha.inputs[0])
            links.new(obj_info.outputs['Alpha'], math_alpha.inputs[1])

            if layer0.alpha < 0.999:
                math_layer_a = nodes.new('ShaderNodeMath')
                math_layer_a.operation = 'MULTIPLY'
                math_layer_a.location = (100, -150)
                links.new(math_alpha.outputs['Value'], math_layer_a.inputs[0])
                math_layer_a.inputs[1].default_value = layer0.alpha
                links.new(math_layer_a.outputs['Value'], bsdf.inputs['Alpha'])
            else:
                links.new(math_alpha.outputs['Value'], bsdf.inputs['Alpha'])

        # Unshaded layer: emits own color for full ambient illumination
        if layer0.shading_flags & 0x1:
            links.new(mix_col.outputs[2], bsdf.inputs['Emission Color'])
            bsdf.inputs['Emission Strength'].default_value = 1.0

    curr_surface_output = bsdf.outputs['BSDF']

    # Process secondary layers (Layer 1, Layer 2...)
    for layer_idx, layer in enumerate(layers[1:], start=1):
        tex = bpyImages[layer.texture_id] if layer.texture_id < len(bpyImages) else None
        if not tex:
            continue

        loc_y = -350 - 250 * (layer_idx - 1)
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = tex
        tex_node.location = (-350, loc_y)

        # Connect Mapping node if texture animation (TVertexAnims) exists
        if layer.texture_animation_id is not None and model and layer.texture_animation_id < len(model.texture_animations):
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-750, loc_y)
            map_node = nodes.new('ShaderNodeMapping')
            map_node.name = f"Mapping_Mat{material_index}_L{layer_idx}"
            map_node.location = (-550, loc_y)
            links.new(coord_node.outputs['UV'], map_node.inputs['Vector'])
            links.new(map_node.outputs['Vector'], tex_node.inputs['Vector'])

        if layer.filter_mode in (3, 4) or (layer.shading_flags & 0x1):
            # Additive overlay layer (e.g. animated star shimmer, energy glow)
            add_shader = nodes.new('ShaderNodeAddShader')
            add_shader.location = (550 + 150 * (layer_idx - 1), 0)

            emis = nodes.new('ShaderNodeEmission')
            emis.location = (350, loc_y)

            mix_c = nodes.new('ShaderNodeMix')
            mix_c.data_type = 'RGBA'
            mix_c.blend_type = 'MULTIPLY'
            mix_c.location = (-100, loc_y)
            mix_c.inputs[0].default_value = 1.0
            links.new(obj_info.outputs['Color'], mix_c.inputs[6])
            links.new(tex_node.outputs['Color'], mix_c.inputs[7])
            links.new(mix_c.outputs[2], emis.inputs['Color'])

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
            links.new(scale_a.outputs['Value'], emis.inputs['Strength'])

            links.new(curr_surface_output, add_shader.inputs[0])
            links.new(emis.outputs['Emission'], add_shader.inputs[1])
            curr_surface_output = add_shader.outputs['Shader']

    links.new(curr_surface_output, output_node.inputs['Surface'])
    return bpyMaterial


def create_mesh_objects(model, importProperties):
    setTeamColor = getattr(importProperties, 'set_team_color', 'RED')
    mdx_path = getattr(importProperties, 'mdx_file_path', '')

    model.normalize_meshes_names()
    bpyImages = []

    # Replaceable textures dictionary (Cliff, Trees, etc.)
    REPLACEABLE_TEXTURE_PATHS = {
        1: 'ReplaceableTextures\\TeamColor\\TeamColor00.blp',
        2: 'ReplaceableTextures\\TeamGlow\\TeamGlow00.blp',
        11: 'ReplaceableTextures\\Cliff\\Cliff0.blp',
        21: '',  # Used by cursors
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

        # Search on disk
        found_path = find_texture_file(imageFile, mdx_path, importProperties)
        bpyImage = None

        if found_path:
            bpyImage = load_or_convert_texture(found_path, tex_stem)

        # Fallbacks for missing files
        if not bpyImage:
            if is_team_color:
                rgb = constants.TEAM_COLORS.get(setTeamColor, (1.0, 0.0, 0.0))
                bpyImage = create_solid_color_image(tex_stem, (rgb[0], rgb[1], rgb[2], 1.0))
            elif is_team_glow:
                rgb = constants.TEAM_COLORS.get(setTeamColor, (1.0, 0.0, 0.0))
                bpyImage = create_solid_color_image(tex_stem, (rgb[0], rgb[1], rgb[2], 0.75))
            else:
                # 32x32 neutral placeholder so glTF exporter has a valid image size
                bpyImage = create_solid_color_image(f"{tex_stem}_placeholder", (0.5, 0.5, 0.5, 1.0), 32, 32)

        bpyImages.append(bpyImage)

    bpyMaterials = []
    for mat_idx, material in enumerate(model.materials):
        bpyMaterial = create_warcraft3_material(material, mat_idx, bpyImages, model)
        bpyMaterials.append(bpyMaterial)

    model.bpy_images = bpyImages
    model.bpy_materials = bpyMaterials

    bpyObjects = []
    for mesh_idx, warCraft3Mesh in enumerate(model.meshes):
        bpyMesh = bpy.data.meshes.new(warCraft3Mesh.name)
        bpyObject = bpy.data.objects.new(warCraft3Mesh.name, bpyMesh)
        bpy.context.collection.objects.link(bpyObject)
        bpyMesh.from_pydata(warCraft3Mesh.vertices, (), warCraft3Mesh.triangles)

        # Smooth shading for game models
        for poly in bpyMesh.polygons:
            poly.use_smooth = True

        # Custom split normals from Warcraft 3
        if hasattr(warCraft3Mesh, 'normals') and warCraft3Mesh.normals and len(warCraft3Mesh.normals) == len(warCraft3Mesh.vertices):
            try:
                bpyMesh.normals_split_custom_set_from_vertices(warCraft3Mesh.normals)
            except Exception:
                pass

        bpyMesh.uv_layers.new()
        uvLayer = bpyMesh.uv_layers.active.data
        for tris in bpyMesh.polygons:
            for loopIndex in range(tris.loop_start, tris.loop_start + tris.loop_total):
                vertexIndex = bpyMesh.loops[loopIndex].vertex_index
                uvLayer[loopIndex].uv = (warCraft3Mesh.uvs[vertexIndex])
        
        if warCraft3Mesh.material_id < len(bpyMaterials):
            bpyMaterial = bpyMaterials[warCraft3Mesh.material_id]
            bpyMesh.materials.append(bpyMaterial)

        # Initialize object color and alpha from geoset animation if present
        ga = next((g for g in model.geoset_animations if g.geoset_id == mesh_idx), None)
        if ga:
            init_c = getattr(ga, 'color', (1.0, 1.0, 1.0))
            init_a = getattr(ga, 'alpha', 1.0)
            bpyObject.color = (init_c[0], init_c[1], init_c[2], init_a)
        else:
            bpyObject.color = (1.0, 1.0, 1.0, 1.0)

        for vertexGroupId in warCraft3Mesh.vertex_groups_ids:
            bpyObject.vertex_groups.new(name=str(vertexGroupId))
            
        for vertexIndex, vertexGroupIds in enumerate(warCraft3Mesh.vertex_groups):
            if not vertexGroupIds:
                continue
            # Weight normalization: sum must equal 1.0 (crucial for Godot Engine and glTF)
            weight = 1.0 / len(vertexGroupIds)
            for vertexGroupId in vertexGroupIds:
                bpyObject.vertex_groups[str(vertexGroupId)].add([vertexIndex, ], weight, 'REPLACE')
                
        bpyObjects.append(bpyObject)

    return bpyObjects


def create_armature_object(model, bpyObjects, boneSize):
    # Sort nodes by objectId so edit_bones index matches node.node.id perfectly
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
    
    for indexNode, node in enumerate(nodes):
        nodePosition = pivotPoints[indexNode] if indexNode < len(pivotPoints) else (0.0, 0.0, 0.0)
        boneName = node.node.name or f"Node_{indexNode}"
        nodeTypes.add(node.type)
        bone = bpyArmature.edit_bones.new(boneName)
        bone.head = nodePosition
        bone.tail = nodePosition
        bone.tail[1] += boneSize
        bone_names.append(bone.name)  # Store exact name assigned by Blender (handles deduplication)
        boneTypes[bone.name] = node.type
        
    nodeTypes = list(nodeTypes)
    nodeTypes.sort()
    
    for indexNode, node in enumerate(nodes):
        bone = bpyObject.data.edit_bones[indexNode]
        if node.node.parent is not None and node.node.parent < len(bpyObject.data.edit_bones):
            parent = bpyObject.data.edit_bones[node.node.parent]
            bone.parent = parent
            
    for mesh in bpyObjects:
        mesh.modifiers.new(name='Armature', type='ARMATURE')
        mesh.modifiers['Armature'].object = bpyObject
        for vertexGroup in mesh.vertex_groups:
            try:
                vertexGroupIndex = int(vertexGroup.name)
                if vertexGroupIndex < len(bone_names):
                    vertexGroup.name = bone_names[vertexGroupIndex]
            except ValueError:
                pass

    bpy.ops.object.mode_set(mode='POSE')
    
    # Bone Collections (Blender 4.0+ / 5.2)
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


def create_armature_actions(armatureObject, model, frameTime, bone_names):
    nodes = model.nodes
    sequences = model.sequences

    old_act = bpy.data.actions.get('#UNANIMATED')
    if old_act and old_act.users == 0:
        try:
            bpy.data.actions.remove(old_act)
        except Exception:
            pass

    action = bpy.data.actions.new(name='#UNANIMATED')
    action.use_fake_user = True
    action['wc3_armature_name'] = armatureObject.name
    action['wc3_sequence_name'] = '#UNANIMATED'
    add_sequence_to_armature('#UNANIMATED', armatureObject, action.name)
    for indexNode, node in enumerate(nodes):
        boneName = bone_names[indexNode]
        dataPath = 'pose.bones["' + boneName + '"]'
        locationFcurveX = create_fcurve(action, armatureObject, dataPath + '.location', index=0)
        locationFcurveY = create_fcurve(action, armatureObject, dataPath + '.location', index=1)
        locationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.location', index=2)
        locationFcurveX.keyframe_points.insert(0.0, 0.0)
        locationFcurveY.keyframe_points.insert(0.0, 0.0)
        locationFcurveZ.keyframe_points.insert(0.0, 0.0)
        rotationFcurveX = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=0)
        rotationFcurveY = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=1)
        rotationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=2)
        rotationFcurveX.keyframe_points.insert(0.0, 0.0)
        rotationFcurveY.keyframe_points.insert(0.0, 0.0)
        rotationFcurveZ.keyframe_points.insert(0.0, 0.0)
        scaleFcurveX = create_fcurve(action, armatureObject, dataPath + '.scale', index=0)
        scaleFcurveY = create_fcurve(action, armatureObject, dataPath + '.scale', index=1)
        scaleFcurveZ = create_fcurve(action, armatureObject, dataPath + '.scale', index=2)
        scaleFcurveX.keyframe_points.insert(0.0, 1.0)
        scaleFcurveY.keyframe_points.insert(0.0, 1.0)
        scaleFcurveZ.keyframe_points.insert(0.0, 1.0)
        
    for sequence in sequences:
        intervalStart = sequence.interval_start
        intervalEnd = sequence.interval_end

        old_act = bpy.data.actions.get(sequence.name)
        if old_act and old_act.users == 0:
            try:
                bpy.data.actions.remove(old_act)
            except Exception:
                pass

        action = bpy.data.actions.new(name=sequence.name)
        action.use_fake_user = True
        action['wc3_armature_name'] = armatureObject.name
        action['wc3_sequence_name'] = sequence.name
        add_sequence_to_armature(sequence.name, armatureObject, action.name)
        for indexNode, node in enumerate(nodes):
            boneName = bone_names[indexNode]
            dataPath = 'pose.bones["' + boneName + '"]'
            translations = node.node.translations
            rotations = node.node.rotations
            scalings = node.node.scalings
            if translations:
                locationFcurveX = None
                locationFcurveY = None
                locationFcurveZ = None
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[translations.interpolation_type]
                for index in range(translations.tracks_count):
                    time = translations.times[index]
                    translation = translations.values[index]
                    if intervalStart <= time and time <= intervalEnd:
                        if not locationFcurveX:
                            locationFcurveX = create_fcurve(action, armatureObject, dataPath + '.location', index=0)
                        if not locationFcurveY:
                            locationFcurveY = create_fcurve(action, armatureObject, dataPath + '.location', index=1)
                        if not locationFcurveZ:
                            locationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.location', index=2)
                        realTime = round((time - intervalStart) / frameTime, 0)
                        locationXKeyframe = locationFcurveX.keyframe_points.insert(realTime, translation[0])
                        locationYKeyframe = locationFcurveY.keyframe_points.insert(realTime, translation[1])
                        locationZKeyframe = locationFcurveZ.keyframe_points.insert(realTime, translation[2])
                        locationXKeyframe.interpolation = interpolationType
                        locationYKeyframe.interpolation = interpolationType
                        locationZKeyframe.interpolation = interpolationType
                if not locationFcurveX:
                    locationFcurveX = create_fcurve(action, armatureObject, dataPath + '.location', index=0)
                    locationFcurveX.keyframe_points.insert(0.0, 0.0)
                if not locationFcurveY:
                    locationFcurveY = create_fcurve(action, armatureObject, dataPath + '.location', index=1)
                    locationFcurveY.keyframe_points.insert(0.0, 0.0)
                if not locationFcurveZ:
                    locationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.location', index=2)
                    locationFcurveZ.keyframe_points.insert(0.0, 0.0)
            if rotations:
                rotationFcurveX = None
                rotationFcurveY = None
                rotationFcurveZ = None
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[rotations.interpolation_type]
                for index in range(rotations.tracks_count):
                    time = rotations.times[index]
                    rotation = rotations.values[index]
                    if intervalStart <= time and time <= intervalEnd:
                        if not rotationFcurveX:
                            rotationFcurveX = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=0)
                        if not rotationFcurveY:
                            rotationFcurveY = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=1)
                        if not rotationFcurveZ:
                            rotationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=2)
                        realTime = round((time - intervalStart) / frameTime, 0)
                        euler = mathutils.Quaternion(mathutils.Vector(rotation)).to_euler('XYZ')
                        rotationXKeyframe = rotationFcurveX.keyframe_points.insert(realTime, euler[0])
                        rotationYKeyframe = rotationFcurveY.keyframe_points.insert(realTime, euler[1])
                        rotationZKeyframe = rotationFcurveZ.keyframe_points.insert(realTime, euler[2])
                        rotationXKeyframe.interpolation = interpolationType
                        rotationYKeyframe.interpolation = interpolationType
                        rotationZKeyframe.interpolation = interpolationType
                if not rotationFcurveX:
                    rotationFcurveX = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=0)
                    rotationFcurveX.keyframe_points.insert(0.0, 0.0)
                if not rotationFcurveY:
                    rotationFcurveY = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=1)
                    rotationFcurveY.keyframe_points.insert(0.0, 0.0)
                if not rotationFcurveZ:
                    rotationFcurveZ = create_fcurve(action, armatureObject, dataPath + '.rotation_euler', index=2)
                    rotationFcurveZ.keyframe_points.insert(0.0, 0.0)
            if scalings:
                scaleFcurveX = None
                scaleFcurveY = None
                scaleFcurveZ = None
                interpolationType = constants.INTERPOLATION_TYPE_NAMES[scalings.interpolation_type]
                for index in range(scalings.tracks_count):
                    time = scalings.times[index]
                    scale = scalings.values[index]
                    if intervalStart <= time and time <= intervalEnd:
                        if not scaleFcurveX:
                            scaleFcurveX = create_fcurve(action, armatureObject, dataPath + '.scale', index=0)
                        if not scaleFcurveY:
                            scaleFcurveY = create_fcurve(action, armatureObject, dataPath + '.scale', index=1)
                        if not scaleFcurveZ:
                            scaleFcurveZ = create_fcurve(action, armatureObject, dataPath + '.scale', index=2)
                        realTime = round((time - intervalStart) / frameTime, 0)
                        scaleXKeyframe = scaleFcurveX.keyframe_points.insert(realTime, scale[0])
                        scaleYKeyframe = scaleFcurveY.keyframe_points.insert(realTime, scale[1])
                        scaleZKeyframe = scaleFcurveZ.keyframe_points.insert(realTime, scale[2])
                        scaleXKeyframe.interpolation = interpolationType
                        scaleYKeyframe.interpolation = interpolationType
                        scaleZKeyframe.interpolation = interpolationType
                if not scaleFcurveX:
                    scaleFcurveX = create_fcurve(action, armatureObject, dataPath + '.scale', index=0)
                    scaleFcurveX.keyframe_points.insert(0.0, 1.0)
                if not scaleFcurveY:
                    scaleFcurveY = create_fcurve(action, armatureObject, dataPath + '.scale', index=1)
                    scaleFcurveY.keyframe_points.insert(0.0, 1.0)
                if not scaleFcurveZ:
                    scaleFcurveZ = create_fcurve(action, armatureObject, dataPath + '.scale', index=2)
                    scaleFcurveZ.keyframe_points.insert(0.0, 1.0)


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
