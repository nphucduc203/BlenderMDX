import bpy
import os
from . import classes
from . import constants
from . import parser
from . import utils
from bpy_extras import io_utils


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

        # Automatically switch 3D Viewport to Material Preview so user immediately sees textures
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
                    if nodeType in {'BONE', 'ATTACHMENT', 'COLLISION_SHAPE', 'EVENT', 'HELPER'}:
                        bone_collection = arm.data.collections.new(collection_name)
                if bone_collection:
                    bone_collection.assign(bone)
        return {'FINISHED'}


class WarCraft3OperatorPushToNLA(bpy.types.Operator):
    bl_idname = 'warcraft_3.push_to_nla'
    bl_label = 'Push All Sequences to NLA'
    bl_description = 'Create NLA tracks for each animation sequence so they are easily accessible in the NLA Editor and exportable to glTF/Godot'
    bl_options = {'UNDO'}

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
        
        # Clear existing NLA tracks to ensure fresh, clean sequence list
        for track in list(arm.animation_data.nla_tracks):
            arm.animation_data.nla_tracks.remove(track)
        
        created = 0
        for seq in wc3.sequencesList:
            if not seq.name:
                continue
            act = bpy.data.actions.get(seq.name)
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


class WarCraft3OperatorExportGodotGLB(bpy.types.Operator, io_utils.ExportHelper):
    bl_idname = 'warcraft_3.export_godot_glb'
    bl_label = 'Export for Godot (.glb)'
    bl_description = 'Export model, embedded textures, and all animation sequences ready for Godot Engine'
    bl_options = {'UNDO'}

    filename_ext = '.glb'
    filter_glob: bpy.props.StringProperty(default='*.glb', options={'HIDDEN'})
    filepath: bpy.props.StringProperty(name='File Path', maxlen=1024, default='')

    exportAllActions: bpy.props.BoolProperty(
        name='Export All Animation Sequences',
        description='Export all model sequences as separate animations for Godot AnimationPlayer',
        default=True
    )

    def execute(self, context):
        arm = find_scene_armature(context)
        if not arm:
            self.report({'ERROR'}, "No Armature found in scene to export")
            return {'CANCELLED'}

        # Ensure active object is arm
        context.view_layer.objects.active = arm
        arm.select_set(True)

        # Ensure all skinned meshes are parented to Armature for glTF
        for obj in context.scene.objects:
            if obj.type == 'MESH':
                for mod in obj.modifiers:
                    if mod.type == 'ARMATURE' and mod.object == arm:
                        if obj.parent != arm:
                            obj.parent = arm
                            obj.matrix_parent_inverse = arm.matrix_world.inverted()

        # Push sequences to NLA tracks so only this model's animations are exported
        if self.exportAllActions:
            bpy.ops.warcraft_3.push_to_nla()

        try:
            bpy.ops.export_scene.gltf(
                filepath=self.filepath,
                export_format='GLB',
                export_animation_mode='NLA_TRACKS' if self.exportAllActions else 'ACTIVE_ACTIONS',
                export_anim_slide_to_zero=True,
                export_optimize_animation_size=True,
                export_image_format='AUTO',
                export_materials='EXPORT',
                export_apply=False,
            )
            self.report({'INFO'}, f"Successfully exported for Godot: {os.path.basename(self.filepath)}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export GLB: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

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
    bl_description = 'Remove Icosphere bone shapes created by Blender when re-importing glTF, revealing the clean model mesh'
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

        # Check for unused Icosphere object created by glTF importer
        for obj in list(bpy.data.objects):
            if obj.type == 'MESH' and 'icosphere' in obj.name.lower():
                in_use = any(b.custom_shape == obj for a in bpy.data.objects if a.type == 'ARMATURE' for b in a.pose.bones)
                if not in_use:
                    bpy.data.objects.remove(obj, do_unlink=True)

        self.report({'INFO'}, f"Cleaned {cleaned_bones} bone shapes. Clean mesh restored!")
        return {'FINISHED'}


class WarCraft3OperatorConvertParticles(bpy.types.Operator):
    bl_idname = 'warcraft_3.convert_particle_emitters'
    bl_label = 'Convert WC3 Particle Emitters'
    bl_description = 'Convert or rebuild Warcraft 3 ParticleEmitter2 into functional Blender particle systems'
    bl_options = {'UNDO'}

    def execute(self, context):
        from . import importer
        arm = find_scene_armature(context)
        if not arm or arm.type != 'ARMATURE':
            self.report({'WARNING'}, "No WarCraft 3 armature found")
            return {'CANCELLED'}

        emitters = importer.WC3_EMITTERS_CACHE.get(arm.name, None)
        bone_names = [b.name for b in arm.data.bones]
        g_scale = arm.get('wc3_global_scale', 0.03)

        # Remove existing particle objects if present
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

