import bpy
import os
import json
import struct
from . import classes
from . import constants
from . import parser
from . import importer
from . import utils
from bpy_extras import io_utils


GLB_MAGIC = 0x46546C67        # b'glTF'
JSON_CHUNK_TYPE = 0x4E4F534A  # b'JSON'
BIN_CHUNK_TYPE = 0x004E4942   # b'BIN\x00'


def postprocess_wc3_glb(glb_path, use_khr_emissive_strength=True):
    """
    Open an exported .glb file, parse its JSON chunk, enforce exact glTF 2.0 material
    properties (`alphaMode`, `alphaCutoff`, `doubleSided`, `pbrMetallicRoughness`,
    `emissiveTexture`, `emissiveFactor`, `KHR_materials_emissive_strength`)
    from each material's `extras`, and write the valid 4-byte-aligned .glb back to disk.
    """
    with open(glb_path, 'rb') as f:
        data = f.read()

    if len(data) < 20:
        return False

    magic, version, total_len = struct.unpack_from('<3I', data, 0)
    if magic != GLB_MAGIC or version != 2:
        return False

    offset = 12
    chunks = []
    json_obj = None
    json_chunk_idx = -1

    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from('<2I', data, offset)
        offset += 8
        chunk_bytes = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == JSON_CHUNK_TYPE and json_obj is None:
            json_str = chunk_bytes.decode('utf-8').rstrip(' \t\r\n\x00')
            json_obj = json.loads(json_str)
            json_chunk_idx = len(chunks)
        chunks.append([chunk_type, chunk_bytes])

    if json_obj is None or json_chunk_idx < 0:
        return False

    extensions_used = set(json_obj.get('extensionsUsed', []))
    materials = json_obj.get('materials', [])

    for mat in materials:
        extras = mat.get('extras')
        if not isinstance(extras, dict):
            continue

        filter_mode = extras.get('wc3_filter_mode', None)
        if filter_mode is None:
            continue
        filter_mode = int(filter_mode)
        unshaded = bool(extras.get('wc3_unshaded', False))
        two_sided = bool(extras.get('wc3_two_sided', False))
        layer_alpha = float(extras.get('wc3_layer_alpha', 1.0))
        self_illum = float(extras.get('wc3_self_illum', 0.0))
        tint = extras.get('wc3_tint', [1.0, 1.0, 1.0, 1.0])
        if not isinstance(tint, (list, tuple)) or len(tint) < 4:
            tint = [1.0, 1.0, 1.0, layer_alpha]

        mat['doubleSided'] = bool(two_sided)

        pbr = mat.setdefault('pbrMetallicRoughness', {})
        pbr['metallicFactor'] = 0.0
        pbr['roughnessFactor'] = 0.85

        base_tex_info = pbr.get('baseColorTexture')
        emis_tex_info = mat.get('emissiveTexture')
        tex_info = base_tex_info or emis_tex_info

        if tex_info and 'baseColorTexture' not in pbr:
            pbr['baseColorTexture'] = dict(tex_info)

        if filter_mode == 0:
            mat['alphaMode'] = 'OPAQUE'
            mat.pop('alphaCutoff', None)
            pbr['baseColorFactor'] = [
                float(tint[0]),
                float(tint[1]),
                float(tint[2]),
                1.0
            ]
        elif filter_mode == 1:
            mat['alphaMode'] = 'MASK'
            mat['alphaCutoff'] = 0.5
            pbr['baseColorFactor'] = [
                float(tint[0]),
                float(tint[1]),
                float(tint[2]),
                1.0
            ]
        elif filter_mode == 2:
            mat['alphaMode'] = 'BLEND'
            mat.pop('alphaCutoff', None)
            pbr['baseColorFactor'] = [
                float(tint[0]),
                float(tint[1]),
                float(tint[2]),
                float(max(min(tint[3], 1.0), 0.05))
            ]
        elif filter_mode in (3, 4):
            mat['alphaMode'] = 'BLEND'
            mat['doubleSided'] = True
            mat.pop('alphaCutoff', None)
            pbr['baseColorFactor'] = [1.0, 1.0, 1.0, 1.0]
            if tex_info:
                mat['emissiveTexture'] = dict(tex_info)
            mat['emissiveFactor'] = [1.0, 1.0, 1.0]
            if use_khr_emissive_strength:
                ext = mat.setdefault('extensions', {})
                ext['KHR_materials_emissive_strength'] = {'emissiveStrength': 2.0}
                extensions_used.add('KHR_materials_emissive_strength')
        elif filter_mode in (5, 6):
            mat['alphaMode'] = 'BLEND'
            mat['doubleSided'] = True
            mat.pop('alphaCutoff', None)
            pbr['baseColorFactor'] = [
                float(tint[0]),
                float(tint[1]),
                float(tint[2]),
                float(max(min(tint[3], 1.0), 0.05))
            ]

        if filter_mode not in (3, 4) and tex_info:
            if unshaded:
                mat['emissiveTexture'] = dict(tex_info)
                mat['emissiveFactor'] = [0.5, 0.5, 0.5]
            elif self_illum > 0.01:
                s_val = float(max(min(self_illum, 1.0), 0.0))
                mat['emissiveTexture'] = dict(tex_info)
                mat['emissiveFactor'] = [s_val, s_val, s_val]

    if extensions_used:
        json_obj['extensionsUsed'] = sorted(extensions_used)

    new_json_bytes = json.dumps(json_obj, separators=(',', ':')).encode('utf-8')
    pad_len = (4 - (len(new_json_bytes) % 4)) % 4
    if pad_len > 0:
        new_json_bytes += b' ' * pad_len

    chunks[json_chunk_idx][1] = new_json_bytes

    new_total_len = 12 + sum(8 + len(c[1]) for c in chunks)
    out = bytearray()
    out += struct.pack('<3I', GLB_MAGIC, 2, new_total_len)
    for c_type, c_bytes in chunks:
        out += struct.pack('<2I', len(c_bytes), c_type)
        out += c_bytes

    with open(glb_path, 'wb') as f:
        f.write(out)

    return True


def find_scene_armature(context):
    arm = utils.get_armature_from_context(context)
    if arm and arm.type == 'ARMATURE':
        return arm
    for obj in context.selected_objects:
        if obj.type == 'ARMATURE':
            return obj
    for obj in context.scene.objects:
        if obj.type == 'ARMATURE':
            return obj
    return None


class WarCraft3OperatorImportMDX(bpy.types.Operator, io_utils.ImportHelper):
    bl_idname = 'warcraft_3.import_mdx'
    bl_label = 'Import *.mdx'
    bl_description = 'Import *.mdx files (3d models of WarCraft 3)'
    bl_options = {'UNDO'}

    filename_ext = '.mdx'
    filter_glob: bpy.props.StringProperty(default='*.mdx', options={'HIDDEN'})
    filepath: bpy.props.StringProperty(name='File Path', maxlen=1024, default='')
    textureSearchDir: bpy.props.StringProperty(
        name='Texture Folder',
        description='Optional directory to search for .blp / image textures',
        maxlen=1024,
        default='',
        subtype='DIR_PATH'
    )
    autoImportTextures: bpy.props.BoolProperty(
        name='Auto Import Textures (.blp)',
        description='Automatically find, convert and load .blp textures',
        default=True
    )
    importParticles: bpy.props.BoolProperty(
        name='Convert Particle Emitters',
        description='Convert Warcraft 3 ParticleEmitter2 into functional Blender particle systems',
        default=True
    )
    useCustomFPS: bpy.props.BoolProperty(name='Use Custom FPS', default=False)
    animationFPS: bpy.props.FloatProperty(name='Animation FPS', default=30.0, min=1.0, max=1000.0)
    globalScale: bpy.props.FloatProperty(
        name='Global Scale',
        default=0.03,
        min=0.0001,
        max=1000.0,
        description="Scale the model on import (0.03 is good for Warcraft III models)"
    )
    boneSize: bpy.props.FloatProperty(name='Bone Size', default=5.0, min=0.0001, max=1000.0)
    teamColor: bpy.props.FloatVectorProperty(
        name='Team Color',
        default=constants.TEAM_COLORS['RED'],
        min=0.0,
        max=1.0,
        size=3,
        subtype='COLOR',
        precision=3
    )
    setTeamColor: bpy.props.EnumProperty(
        items=[
            ('RED', 'Red', ''),
            ('DARK_BLUE', 'Dark Blue', ''),
            ('TURQUOISE', 'Turquoise', ''),
            ('VIOLET', 'Violet', ''),
            ('YELLOW', 'Yellow', ''),
            ('ORANGE', 'Orange', ''),
            ('GREEN', 'Green', ''),
            ('PINK', 'Pink', ''),
            ('GREY', 'Grey', ''),
            ('BLUE', 'Blue', ''),
            ('DARK_GREEN', 'Dark Green', ''),
            ('BROWN', 'Brown', ''),
            ('BLACK', 'Black', '')
        ],
        name='Set Team Color',
        update=utils.set_team_color_property,
        default='RED'
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'autoImportTextures')
        if self.autoImportTextures:
            layout.prop(self, 'textureSearchDir')
        layout.prop(self, 'importParticles')

        layout.separator()
        split = layout.split(factor=0.9)
        subSplit = split.split(factor=0.5)
        subSplit.label(text='Team Color:')
        subSplit.prop(self, 'setTeamColor', text='')
        split.prop(self, 'teamColor', text='')
        layout.prop(self, 'globalScale')
        layout.prop(self, 'boneSize')
        layout.prop(self, 'useCustomFPS')
        if self.useCustomFPS:
            layout.prop(self, 'animationFPS')

    def execute(self, context):
        importProperties = classes.MDXImportProperties()
        importProperties.mdx_file_path = str(self.filepath)
        importProperties.texture_search_dir = str(self.textureSearchDir)
        importProperties.auto_import_textures = bool(self.autoImportTextures)
        importProperties.import_particles = bool(self.importParticles)
        importProperties.set_team_color = str(self.setTeamColor)
        importProperties.bone_size = float(self.boneSize)
        importProperties.use_custom_fps = bool(self.useCustomFPS)
        importProperties.fps = float(self.animationFPS)
        importProperties.global_scale = float(self.globalScale)
        importProperties.calculate_frame_time()
        try:
            parser.load_mdx(importProperties)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to import MDX: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class WarCraft3OperatorAddSequenceToArmature(bpy.types.Operator):
    bl_idname = 'warcraft_3.add_sequence_to_armature'
    bl_label = 'WarCraft 3 Add Sequence to Armature'
    bl_description = 'WarCraft 3 Add Sequence to Armature'
    bl_options = {'UNDO'}

    def execute(self, context):
        arm = find_scene_armature(context)
        if arm and arm.type == 'ARMATURE':
            warcraft3data = arm.data.warcraft_3
            sequence = warcraft3data.sequencesList.add()
            sequence.name = '#UNANIMATED'
        return {'FINISHED'}


class WarCraft3OperatorRemoveSequenceToArmature(bpy.types.Operator):
    bl_idname = 'warcraft_3.remove_sequence_to_armature'
    bl_label = 'WarCraft 3 Remove Sequence to Armature'
    bl_description = 'WarCraft 3 Remove Sequence to Armature'
    bl_options = {'UNDO'}

    def execute(self, context):
        arm = find_scene_armature(context)
        if arm and arm.type == 'ARMATURE':
            warcraft3data = arm.data.warcraft_3
            if 0 <= warcraft3data.sequencesListIndex < len(warcraft3data.sequencesList):
                warcraft3data.sequencesList.remove(warcraft3data.sequencesListIndex)
        return {'FINISHED'}


class WarCraft3OperatorUpdateBoneSettings(bpy.types.Operator):
    bl_idname = 'warcraft_3.update_bone_settings'
    bl_label = 'WarCraft 3 Update Bone Settings'
    bl_description = 'WarCraft 3 Update Bone Settings'
    bl_options = {'UNDO'}

    def execute(self, context):
        arm = find_scene_armature(context)
        if arm and arm.type == 'ARMATURE':
            for bone in arm.data.bones:
                nodeType = getattr(bone.warcraft_3, 'nodeType', None)
                if not nodeType:
                    continue
                collection_name = nodeType.lower() + 's'
                bone_collection = arm.data.collections.get(collection_name)
                if not bone_collection:
                    if nodeType in {'BONE', 'ATTACHMENT', 'COLLISION_SHAPE', 'EVENT', 'HELPER', 'EMITTER', 'RIBBON', 'LIGHT'}:
                        bone_collection = arm.data.collections.new(collection_name)
                if bone_collection:
                    bone_collection.assign(bone)
        return {'FINISHED'}


class WarCraft3OperatorPushToNLA(bpy.types.Operator):
    bl_idname = 'warcraft_3.push_to_nla'
    bl_label = 'Push All Sequences to NLA'
    bl_description = 'Create NLA tracks for each animation sequence so they are easily accessible in the NLA Editor and exportable to glTF/Godot'
    bl_options = {'UNDO'}

    includeUnanimated: bpy.props.BoolProperty(
        name='Include #UNANIMATED Track',
        default=False
    )

    def execute(self, context):
        arm = find_scene_armature(context)
        if not arm:
            self.report({'WARNING'}, "No Warcraft 3 armature found")
            return {'CANCELLED'}
        if not arm.animation_data:
            arm.animation_data_create()

        wc3 = getattr(arm.data, 'warcraft_3', None)
        if not wc3 or not wc3.sequencesList:
            self.report({'WARNING'}, "No animation sequences found on armature")
            return {'CANCELLED'}

        for track in list(arm.animation_data.nla_tracks):
            arm.animation_data.nla_tracks.remove(track)
        for child in arm.children:
            if child.animation_data:
                for track in list(child.animation_data.nla_tracks):
                    child.animation_data.nla_tracks.remove(track)
                if child.type == 'MESH':
                    child.animation_data.action = None

        created = 0
        for seq in wc3.sequencesList:
            if not seq.name:
                continue
            if seq.name == '#UNANIMATED' and not self.includeUnanimated:
                continue
            act = bpy.data.actions.get(seq.name)
            if not act:
                for a in bpy.data.actions:
                    if a.get('wc3_armature_name') == arm.name and a.get('wc3_sequence_name') == seq.name and not a.get('wc3_object_name'):
                        act = a
                        break
            if not act:
                continue
            track = arm.animation_data.nla_tracks.new()
            track.name = seq.name
            start_frame = int(round(act.frame_range[0])) if hasattr(act, 'frame_range') else 0
            strip = track.strips.new(seq.name, start_frame, act)
            if hasattr(strip, 'action_slot') and strip.action_slot is None:
                if hasattr(strip, 'action_suitable_slots') and len(strip.action_suitable_slots) > 0:
                    strip.action_slot = strip.action_suitable_slots[0]
                elif hasattr(act, 'slots') and len(act.slots) > 0:
                    strip.action_slot = act.slots[0]
            track.mute = False
            created += 1

        self.report({'INFO'}, f"Pushed {created} animation sequences to NLA tracks on {arm.name}")
        return {'FINISHED'}


def _build_gltf_material_from_nodes(tex_img, filter_mode, unshaded=False, two_sided=False, tint_rgb=(1.0, 1.0, 1.0), effective_alpha=1.0, self_illum=0.0, mat_name="GLTF_Mat", src_meta=None):
    """
    Create a single-layer glTF-exporter-ready Principled BSDF material.
    """
    additive = filter_mode in (3, 4)
    flat = bpy.data.materials.new(mat_name)
    flat.use_nodes = True
    flat.use_backface_culling = False if (two_sided or filter_mode in (3, 4)) else True

    if filter_mode == 0:
        if hasattr(flat, 'blend_method'):
            flat.blend_method = 'OPAQUE'
        if hasattr(flat, 'surface_render_method'):
            flat.surface_render_method = 'DITHERED'
    elif filter_mode == 1:
        if hasattr(flat, 'blend_method'):
            flat.blend_method = 'CLIP'
        if hasattr(flat, 'alpha_threshold'):
            flat.alpha_threshold = 0.5
        if hasattr(flat, 'surface_render_method'):
            flat.surface_render_method = 'DITHERED'
    else:
        if hasattr(flat, 'blend_method'):
            flat.blend_method = 'BLEND'
        if hasattr(flat, 'surface_render_method'):
            flat.surface_render_method = 'BLENDED'

    fn = flat.node_tree.nodes
    fl = flat.node_tree.links
    fn.clear()
    out = fn.new('ShaderNodeOutputMaterial')
    out.location = (400, 0)

    export_img = tex_img
    if additive and tex_img is not None:
        try:
            export_img = importer.bake_alpha_to_rgb_for_additive_texture(
                tex_img, tint_rgb=tint_rgb, layer_alpha=effective_alpha
            )
        except Exception:
            export_img = tex_img

    tex = fn.new('ShaderNodeTexImage')
    tex.image = export_img
    tex.location = (-350, 0)

    bsdf = fn.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (100, 0)
    if 'Roughness' in bsdf.inputs:
        bsdf.inputs['Roughness'].default_value = 0.85
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = 0.0
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.0

    fl.new(tex.outputs['Color'], bsdf.inputs['Base Color'])

    if filter_mode == 1:
        rnd = fn.new('ShaderNodeMath')
        rnd.operation = 'ROUND'
        rnd.location = (-100, -150)
        fl.new(tex.outputs['Alpha'], rnd.inputs[0])
        fl.new(rnd.outputs['Value'], bsdf.inputs['Alpha'])
    elif filter_mode >= 2:
        fl.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])

    if unshaded or additive:
        fl.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = 2.0 if additive else 0.5
    elif self_illum > 0.01:
        fl.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = float(self_illum)

    fl.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    if src_meta:
        for k, v in src_meta.items():
            if not k.startswith('_') and k != 'wc3_sec_layers':
                flat[k] = v
    flat['wc3_filter_mode'] = int(filter_mode)
    flat['wc3_blend'] = importer.FILTER_MODE_NAMES.get(filter_mode, 'none')
    flat['wc3_tint'] = [float(tint_rgb[0]), float(tint_rgb[1]), float(tint_rgb[2]), float(effective_alpha)]
    flat['wc3_layer_alpha'] = float(effective_alpha)
    flat['wc3_self_illum'] = float(self_illum)
    flat['wc3_unshaded'] = bool(unshaded or additive)
    flat['wc3_two_sided'] = bool(two_sided or filter_mode in (3, 4))
    return flat


def _flatten_wc3_material(src, obj_color=(1.0, 1.0, 1.0, 1.0)):
    """Build a glTF-friendly copy of a WarCraft 3 material's primary layer."""
    if not src or not src.use_nodes:
        return None
    nodes = src.node_tree.nodes
    img = None
    for n in nodes:
        if n.type == 'TEX_IMAGE' and n.image:
            img = n.image
            break
    if img is None:
        return None

    filter_mode = src.get('wc3_filter_mode', None)
    if filter_mode is None:
        has_bsdf = any(n.type == 'BSDF_PRINCIPLED' for n in nodes)
        has_add = any(n.type == 'ADD_SHADER' for n in nodes)
        if has_add and not has_bsdf:
            filter_mode = 3
        elif getattr(src, 'blend_method', '') == 'CLIP':
            filter_mode = 1
        elif getattr(src, 'blend_method', '') == 'BLEND' or getattr(src, 'surface_render_method', '') == 'BLENDED':
            filter_mode = 2
        else:
            filter_mode = 0

    unshaded = bool(src.get('wc3_unshaded', False))
    two_sided = bool(src.get('wc3_two_sided', not src.use_backface_culling))
    self_illum = float(src.get('wc3_self_illum', 0.0))
    if self_illum <= 0.001 and filter_mode == 0:
        has_bsdf = any(n.type == 'BSDF_PRINCIPLED' for n in nodes)
        has_add = any(n.type == 'ADD_SHADER' for n in nodes)
        if has_bsdf and has_add:
            self_illum = 0.20

    tint_rgb = (float(obj_color[0]), float(obj_color[1]), float(obj_color[2]))
    obj_alpha = float(obj_color[3]) if len(obj_color) > 3 else 1.0
    effective_alpha = max(min(obj_alpha, 1.0), 0.15)

    return _build_gltf_material_from_nodes(
        img, filter_mode, unshaded=unshaded, two_sided=two_sided,
        tint_rgb=tint_rgb, effective_alpha=effective_alpha,
        self_illum=self_illum, mat_name='GLTF_' + src.name, src_meta=src
    )


def _is_blender_obj_halo_cloud(obj):
    """
    Check if a Blender Mesh Object is a stacked additive halo quad cloud (like Geoset 17 in
    HeroMoonPriestess: 84 vertices = 21 disconnected 4-vertex quads with an Additive material).
    Works both on newly imported models (`wc3_is_halo_cloud`) and existing `.blend` scenes.
    """
    if bool(obj.get('wc3_is_halo_cloud', False)):
        return True
    mesh = getattr(obj, 'data', None)
    if not mesh or not hasattr(mesh, 'vertices') or not hasattr(mesh, 'polygons'):
        return False
    v_cnt = len(mesh.vertices)
    p_cnt = len(mesh.polygons)
    if v_cnt >= 16 and (v_cnt % 4 == 0) and p_cnt == (v_cnt // 2):
        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue
            if mat.get('wc3_filter_mode') in (3, 4):
                return True
            if mat.use_nodes and mat.node_tree:
                n_types = {n.type for n in mat.node_tree.nodes}
                if 'ADD_SHADER' in n_types and 'BSDF_PRINCIPLED' not in n_types:
                    return True
    return False


def _is_blender_obj_outline_shell(obj):
    """
    Check if a Blender Mesh Object is an inverted-hull toon outline shell (like Geosets 10, 11, 12, 13
    in HeroMoonPriestess). Works both on newly imported models (`wc3_is_outline_shell`) and existing
    `.blend` scenes.
    """
    if bool(obj.get('wc3_is_outline_shell', False)):
        return True
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        if not mat.use_backface_culling:
            continue
        is_blend = (
            mat.get('wc3_filter_mode') == 2
            or getattr(mat, 'blend_method', '') == 'BLEND'
            or getattr(mat, 'surface_render_method', '') == 'BLENDED'
        )
        if is_blend and mat.use_nodes and mat.node_tree:
            # Check if it's a single-texture unshaded blend shell with backface culling enabled
            tex_nodes = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
            bsdf_nodes = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
            if len(tex_nodes) == 1 and len(bsdf_nodes) == 1:
                bsdf = bsdf_nodes[0]
                emis_in = bsdf.inputs.get('Emission Color') if hasattr(bsdf.inputs, 'get') else None
                if bool(mat.get('wc3_unshaded', False)) or (emis_in and getattr(emis_in, 'is_linked', False)):
                    return True
    return False


def _prepare_export_meshes_and_materials(context, arm, export_set):
    swaps = []
    temp_materials = []
    temp_meshes_objs = []
    by_key = {}

    for obj in list(export_set):
        if obj.type != 'MESH':
            continue
        for i, slot in enumerate(obj.material_slots):
            src = slot.material
            if not src or not src.use_nodes:
                continue
            col = tuple(obj.color) if hasattr(obj, 'color') else (1.0, 1.0, 1.0, 1.0)
            bake_a = col[3]
            if bake_a < 0.05:
                bake_a = float(obj.get('wc3_max_alpha', 1.0))
                if bake_a < 0.05:
                    bake_a = 1.0
            bake_col = (col[0], col[1], col[2], bake_a)

            key = (src.name, round(bake_col[0], 3), round(bake_col[1], 3), round(bake_col[2], 3), round(bake_col[3], 3))
            flat = by_key.get(key)
            if flat is None:
                flat = _flatten_wc3_material(src, bake_col)
                by_key[key] = flat
                if flat:
                    temp_materials.append(flat)
            if flat:
                slot.material = flat
                swaps.append((obj, i, src))
                obj['wc3_filter_mode'] = int(flat.get('wc3_filter_mode', 0))
                obj['wc3_blend'] = str(flat.get('wc3_blend', 'none'))
                obj['wc3_color'] = [float(c) for c in bake_col]

            sec_layers = src.get('wc3_sec_layers', [])
            if sec_layers:
                for sec_info in sec_layers:
                    if sec_info.get('same_as_base', False):
                        continue
                    sec_tex_name = sec_info.get('tex_name', '')
                    sec_img = bpy.data.images.get(sec_tex_name)
                    if not sec_img or 'placeholder' in sec_img.name.lower():
                        continue
                    sec_idx = sec_info.get('layer_index', 1)
                    sec_alpha = float(sec_info.get('alpha', 0.5)) * bake_col[3]
                    sec_key = (src.name, f"L{sec_idx}", sec_img.name, round(bake_col[0], 3), round(bake_col[1], 3), round(bake_col[2], 3))
                    sec_mat = by_key.get(sec_key)
                    if sec_mat is None:
                        sec_mat = _build_gltf_material_from_nodes(
                            sec_img, filter_mode=int(sec_info.get('filter_mode', 3)),
                            unshaded=True, two_sided=bool(sec_info.get('two_sided', True)),
                            tint_rgb=(bake_col[0], bake_col[1], bake_col[2]),
                            effective_alpha=sec_alpha,
                            mat_name=f"GLTF_{src.name}_L{sec_idx}"
                        )
                        by_key[sec_key] = sec_mat
                        temp_materials.append(sec_mat)

                    dup_mesh = obj.data.copy()
                    dup_mesh.materials.clear()
                    dup_mesh.materials.append(sec_mat)
                    dup_obj = obj.copy()
                    dup_obj.name = f"{obj.name}_OverlayL{sec_idx}"
                    dup_obj.data = dup_mesh
                    context.scene.collection.objects.link(dup_obj)
                    export_set.add(dup_obj)
                    temp_meshes_objs.append((dup_obj, dup_mesh))

    return swaps, temp_materials, temp_meshes_objs


class WarCraft3OperatorExportGodotGLB(bpy.types.Operator, io_utils.ExportHelper):
    bl_idname = 'warcraft_3.export_godot_glb'
    bl_label = 'Export for Godot (.glb)'
    bl_description = 'Export model, embedded textures, and all animation sequences ready for Godot Engine & Blender'
    bl_options = {'UNDO'}

    filename_ext = '.glb'
    filter_glob: bpy.props.StringProperty(default='*.glb', options={'HIDDEN'})
    filepath: bpy.props.StringProperty(name='File Path', maxlen=1024, default='')

    exportAllActions: bpy.props.BoolProperty(
        name='Export All Animation Sequences',
        description='Export all model sequences as separate animations for Godot AnimationPlayer & Blender',
        default=True
    )
    skipStackedHaloClouds: bpy.props.BoolProperty(
        name='Exclude Stacked Additive Halo Quads (Fixes Black Boxes)',
        description='Exclude Geosets composed of dozens of intersecting Additive Halo Quads (such as Geoset 17 in HeroMoonPriestess) that cause black box walls in glTF',
        default=True
    )
    skipOutlineShells: bpy.props.BoolProperty(
        name='Exclude Inverted-Hull Rim Shells (Fixes Flat Blue Tiger)',
        description='Exclude inverted-hull toon outline shell Geosets (such as Geosets 10, 11, 12, 13)',
        default=True
    )
    skipHiddenSpellMeshes: bpy.props.BoolProperty(
        name='Exclude Hidden / Unanimated Effect Meshes',
        description='Exclude Geosets whose alpha is 0 across all animations',
        default=True
    )
    exportCamerasAndLights: bpy.props.BoolProperty(
        name='Export WC3 Portrait Cameras & Lights',
        description='Include WarCraft 3 portrait camera and light objects in the exported .glb',
        default=False
    )

    def execute(self, context):
        arm = find_scene_armature(context)
        if not arm:
            self.report({'ERROR'}, "No Armature found in scene to export")
            return {'CANCELLED'}

        context.view_layer.objects.active = arm

        for obj in context.scene.objects:
            if obj.type == 'MESH':
                for mod in obj.modifiers:
                    if mod.type == 'ARMATURE' and mod.object == arm:
                        if obj.parent != arm:
                            obj.parent = arm
                            obj.matrix_parent_inverse = arm.matrix_world.inverted()

        export_set = {arm}
        for child in list(arm.children):
            if child.name.startswith('W3_Inst_') or child.name.startswith('W3_Emitter_'):
                continue
            if child.type == 'MESH':
                if self.skipHiddenSpellMeshes and float(child.get('wc3_max_alpha', 1.0)) < 0.02:
                    continue
                if self.skipOutlineShells and _is_blender_obj_outline_shell(child):
                    continue
                if self.skipStackedHaloClouds and _is_blender_obj_halo_cloud(child):
                    continue
                export_set.add(child)
            elif self.exportCamerasAndLights and child.type in {'CAMERA', 'LIGHT', 'EMPTY'}:
                export_set.add(child)

        saved_action = arm.animation_data.action if arm.animation_data else None

        if self.exportAllActions:
            bpy.ops.warcraft_3.push_to_nla(includeUnanimated=False)
            if arm.animation_data:
                arm.animation_data.action = None

        swaps, temp_materials, temp_meshes_objs = _prepare_export_meshes_and_materials(context, arm, export_set)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in export_set:
            obj.select_set(True)
        context.view_layer.objects.active = arm

        try:
            bpy.ops.export_scene.gltf(
                filepath=self.filepath,
                export_format='GLB',
                use_selection=True,
                export_animation_mode='NLA_TRACKS' if self.exportAllActions else 'ACTIVE_ACTIONS',
                export_anim_slide_to_zero=True,
                export_optimize_animation_size=False,
                export_image_format='AUTO',
                export_materials='EXPORT',
                export_cameras=bool(self.exportCamerasAndLights),
                export_apply=False,
                export_extras=True,
            )
            postprocess_wc3_glb(self.filepath, use_khr_emissive_strength=True)
            self.report({'INFO'}, f"Successfully exported for Godot: {os.path.basename(self.filepath)}")
            result = {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export GLB: {e}")
            import traceback
            traceback.print_exc()
            result = {'CANCELLED'}
        finally:
            if arm.animation_data and saved_action:
                arm.animation_data.action = saved_action
            for obj, idx, src in swaps:
                try:
                    obj.material_slots[idx].material = src
                except Exception:
                    pass
            for dup_obj, dup_mesh in temp_meshes_objs:
                try:
                    bpy.data.objects.remove(dup_obj, do_unlink=True)
                except Exception:
                    pass
                try:
                    bpy.data.meshes.remove(dup_mesh, do_unlink=True)
                except Exception:
                    pass
            for tmp in temp_materials:
                try:
                    bpy.data.materials.remove(tmp, do_unlink=True)
                except Exception:
                    pass
        return result

    def invoke(self, context, event):
        arm = find_scene_armature(context)
        if arm:
            safe_name = "".join(c for c in arm.name.replace(' Nodes', '') if c.isalnum() or c in ('_', '-'))
            if not safe_name:
                safe_name = "warcraft_model"
            self.filepath = safe_name + ".glb"
        return super().invoke(context, event)


class WarCraft3OperatorCleanBoneShapes(bpy.types.Operator):
    bl_idname = 'warcraft_3.clean_bone_shapes'
    bl_label = 'Fix glTF Display (Hide Spheres)'
    bl_description = 'Remove Icosphere bone shapes created by Blender when re-importing glTF, fix EEVEE Next BLENDED materials, and populate sequence list from NLA tracks'
    bl_options = {'UNDO'}

    def execute(self, context):
        cleaned_bones = 0
        arm = find_scene_armature(context)
        armatures = [arm] if arm else [o for o in context.scene.objects if o.type == 'ARMATURE']

        for a in armatures:
            a.data.display_type = 'STICK'
            for b in a.pose.bones:
                if b.custom_shape:
                    b.custom_shape = None
                    cleaned_bones += 1

            if hasattr(a.data, 'warcraft_3') and a.animation_data and a.animation_data.nla_tracks:
                wc3 = a.data.warcraft_3
                if len(wc3.sequencesList) == 0:
                    for track in a.animation_data.nla_tracks:
                        if track.strips:
                            strip = track.strips[0]
                            if strip.action:
                                item = wc3.sequencesList.add()
                                item.name = track.name
                                item.action_name = strip.action.name
                    if len(wc3.sequencesList) > 0:
                        wc3.sequencesListIndex = 0

        for obj in list(bpy.data.objects):
            if obj.type == 'MESH' and 'icosphere' in obj.name.lower():
                in_use = any(b.custom_shape == obj for a in bpy.data.objects if a.type == 'ARMATURE' for b in a.pose.bones)
                if not in_use:
                    bpy.data.objects.remove(obj, do_unlink=True)
            elif obj.type == 'MESH':
                for slot in obj.material_slots:
                    mat = slot.material
                    if mat and mat.get('wc3_filter_mode', 0) >= 2:
                        if hasattr(mat, 'surface_render_method'):
                            mat.surface_render_method = 'BLENDED'

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D' and space.shading.type == 'SOLID':
                        space.shading.type = 'MATERIAL'

        self.report({'INFO'}, f"Cleaned {cleaned_bones} bone shapes and restored animation list!")
        return {'FINISHED'}


class WarCraft3OperatorConvertParticles(bpy.types.Operator):
    bl_idname = 'warcraft_3.convert_particle_emitters'
    bl_label = 'Convert WC3 Particle Emitters'
    bl_description = 'Convert or rebuild Warcraft 3 ParticleEmitter2 into functional Blender particle systems'
    bl_options = {'UNDO'}

    def execute(self, context):
        arm = find_scene_armature(context)
        if not arm or arm.type != 'ARMATURE':
            self.report({'WARNING'}, "No WarCraft 3 armature found")
            return {'CANCELLED'}

        emitters = importer.WC3_EMITTERS_CACHE.get(arm.name, None)
        bone_names = [b.name for b in arm.data.bones]
        g_scale = arm.get('wc3_global_scale', 0.03)

        col = bpy.data.collections.get("WarCraft 3 Particles")
        if col:
            for obj in list(col.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            for child_col in list(col.children):
                for obj in list(child_col.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.collections.remove(child_col)
            bpy.data.collections.remove(col)

        if not emitters:
            self.report({'WARNING'}, "No ParticleEmitter2 data found on armature")
            return {'CANCELLED'}

        class DummyModel:
            pass
        dm = DummyModel()
        dm.particle_emitters_2 = emitters
        bpyImages = [img for img in bpy.data.images if not img.name.startswith('Render')]
        created = importer.create_particle_emitter_systems(dm, arm, bone_names, bpyImages, g_scale)
        self.report({'INFO'}, f"Converted {len(created)} particle emitter systems in 'WarCraft 3 Particles' collection")
        return {'FINISHED'}


class WarCraft3OperatorToggleParticles(bpy.types.Operator):
    bl_idname = 'warcraft_3.toggle_particles'
    bl_label = 'Toggle Particle Visibility'
    bl_description = 'Show or hide the WarCraft 3 Particles collection in viewport'
    bl_options = {'UNDO'}

    def execute(self, context):
        col = bpy.data.collections.get("WarCraft 3 Particles")
        if not col:
            self.report({'WARNING'}, "No 'WarCraft 3 Particles' collection found")
            return {'CANCELLED'}
        col.hide_viewport = not col.hide_viewport
        col.hide_render = col.hide_viewport
        status = "Hidden" if col.hide_viewport else "Visible"
        self.report({'INFO'}, f"WarCraft 3 Particles is now {status}")
        return {'FINISHED'}
