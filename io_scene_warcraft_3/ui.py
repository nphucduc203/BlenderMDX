import bpy
from . import utils


class WARCRAFT3_PT_viewport(bpy.types.Panel):
    bl_idname = 'WARCRAFT3_PT_viewport'
    bl_label = 'WarCraft 3 Animations'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'WarCraft 3'

    @classmethod
    def poll(cls, context):
        return utils.get_armature_from_context(context) is not None

    def draw(self, context):
        arm = utils.get_armature_from_context(context)
        if not arm:
            return
        warcraft3data = arm.data.warcraft_3
        layout = self.layout
        
        # Model Info Box
        box = layout.box()
        box.label(text=f"Model: {arm.name}", icon='ARMATURE_DATA')
        curr_act = arm.animation_data.action if arm.animation_data else None
        if curr_act:
            f_start = bpy.context.scene.frame_start
            f_end = bpy.context.scene.frame_end
            box.label(text=f"Active: {curr_act.name} ({f_start}-{f_end})", icon='ACTION')
        
        # Play / Pause controls
        row = layout.row(align=True)
        if context.screen.is_animation_playing:
            row.operator('screen.animation_play', text='Pause Animation', icon='PAUSE')
        else:
            row.operator('screen.animation_play', text='Play Animation', icon='PLAY')
            
        layout.label(text='Animation Sequences (Click to Play):')
        row = layout.row()
        row.template_list(
            listtype_name='UI_UL_list',
            list_id='name',
            dataptr=warcraft3data,
            propname='sequencesList',
            active_dataptr=warcraft3data,
            active_propname='sequencesListIndex',
            rows=6
        )
        col = row.column(align=True)
        col.operator('warcraft_3.add_sequence_to_armature', icon='ADD', text='')
        col.operator('warcraft_3.remove_sequence_to_armature', icon='REMOVE', text='')
        
        # Particle Systems Controls
        layout.separator()
        box_part = layout.box()
        box_part.label(text='WarCraft 3 Particles:', icon='PARTICLES')
        row_p = box_part.row(align=True)
        row_p.operator('warcraft_3.convert_particle_emitters', text='Convert Particles', icon='FILE_REFRESH')
        row_p.operator('warcraft_3.toggle_particles', text='Show/Hide Particles', icon='HIDE_OFF')

        # Godot Engine Tools
        layout.separator()
        box_godot = layout.box()
        box_godot.label(text='Godot Engine Export:', icon='EXPORT')
        box_godot.operator('warcraft_3.export_godot_glb', text='Export for Godot (.glb)', icon='FILE_3D')
        box_godot.operator('warcraft_3.push_to_nla', text='Push All to NLA Tracks', icon='NLA')

        layout.separator()
        layout.operator('warcraft_3.clean_bone_shapes', text='Fix glTF Display (Hide Spheres)', icon='HIDE_OFF')


class WARCRAFT3_PT_armature(bpy.types.Panel):
    bl_idname = 'WARCRAFT3_PT_armature'
    bl_label = 'WarCraft 3'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'

    @classmethod
    def poll(cls, context):
        return utils.get_armature_from_context(context) is not None

    def draw(self, context):
        arm = utils.get_armature_from_context(context)
        if not arm:
            return
        warcraft3data = arm.data.warcraft_3
        layout = self.layout
        
        # Play / Pause controls
        row = layout.row(align=True)
        if context.screen.is_animation_playing:
            row.operator('screen.animation_play', text='Pause Animation', icon='PAUSE')
        else:
            row.operator('screen.animation_play', text='Play Animation', icon='PLAY')
            
        layout.label(text='Animations:')
        row = layout.row()
        row.template_list(
            listtype_name='UI_UL_list',
            list_id='name',
            dataptr=warcraft3data,
            propname='sequencesList',
            active_dataptr=warcraft3data,
            active_propname='sequencesListIndex',
            rows=4
        )
        col = row.column(align=True)
        col.operator('warcraft_3.add_sequence_to_armature', icon='ADD', text='')
        col.operator('warcraft_3.remove_sequence_to_armature', icon='REMOVE', text='')

        layout.separator()
        layout.operator('warcraft_3.export_godot_glb', text='Export for Godot (.glb)', icon='FILE_3D')
        layout.operator('warcraft_3.push_to_nla', icon='NLA', text='Push All to NLA Tracks')


class WARCRAFT3_PT_bone(bpy.types.Panel):
    bl_idname = 'WARCRAFT3_PT_bone'
    bl_label = 'WarCraft 3'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'bone'

    @classmethod
    def poll(cls, context):
        return context.bone

    def draw(self, context):
        bone = context.bone
        warcraft3data = bone.warcraft_3
        layout = self.layout
        layout.prop(warcraft3data, 'nodeType')
        if context.object and context.object.mode == 'POSE':
            layout.operator(
                'warcraft_3.update_bone_settings',
                text='Update All Nodes'
            )
