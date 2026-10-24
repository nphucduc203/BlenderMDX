import bpy
from . import constants


ACTION_NAME_UNANIMATED = '#UNANIMATED'


def get_armature_from_context(context):
    obj = getattr(context, 'object', None)
    if obj:
        if obj.type == 'ARMATURE' and hasattr(obj.data, 'warcraft_3'):
            return obj
        if obj.parent and obj.parent.type == 'ARMATURE' and hasattr(obj.parent.data, 'warcraft_3'):
            return obj.parent
        for mod in getattr(obj, 'modifiers', []):
            if mod.type == 'ARMATURE' and mod.object and hasattr(mod.object.data, 'warcraft_3'):
                return mod.object

    # Fallback to selected objects
    for o in getattr(context, 'selected_objects', []):
        if o.type == 'ARMATURE' and hasattr(o.data, 'warcraft_3'):
            return o

    # Fallback to any warcraft_3 armature in current scene
    scene = getattr(context, 'scene', None) or bpy.context.scene
    for o in scene.objects:
        if o.type == 'ARMATURE' and hasattr(o.data, 'warcraft_3'):
            return o

    return None


def set_animation(self, context):
    # 1. Direct identification of armature from self (which is warcraft_3 on Armature data)
    arm_data = getattr(self, 'id_data', None)
    armatureObject = None
    if arm_data and isinstance(arm_data, bpy.types.Armature):
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE' and obj.data == arm_data:
                armatureObject = obj
                break
    if not armatureObject:
        armatureObject = get_armature_from_context(context)
    if not armatureObject or not hasattr(armatureObject.data, 'warcraft_3'):
        return

    wc3 = armatureObject.data.warcraft_3
    if not wc3.sequencesList or wc3.sequencesListIndex < 0 or wc3.sequencesListIndex >= len(wc3.sequencesList):
        return

    seq_item = wc3.sequencesList[wc3.sequencesListIndex]
    setAnimationName = seq_item.name
    target_action_name = getattr(seq_item, 'action_name', None) or setAnimationName

    # 2. Retrieve exact action created for this sequence and armature
    setAction = bpy.data.actions.get(target_action_name)
    if not setAction:
        for a in bpy.data.actions:
            if a.get('wc3_armature_name') == armatureObject.name and a.get('wc3_sequence_name') == setAnimationName:
                setAction = a
                break
    if not setAction:
        setAction = bpy.data.actions.get(setAnimationName)

    if setAction:
        if armatureObject.animation_data is None:
            armatureObject.animation_data_create()
        armatureObject.animation_data.action = setAction
        if hasattr(setAction, 'frame_range'):
            bpy.context.scene.frame_start = int(round(setAction.frame_range[0]))
            bpy.context.scene.frame_end = int(round(setAction.frame_range[1]))
            bpy.context.scene.frame_current = bpy.context.scene.frame_start

    # 3. Synchronize child mesh actions for this sequence without cross-contaminating other models
    for child in armatureObject.children:
        if child.type == 'MESH':
            child_act = None
            for a in bpy.data.actions:
                if a.get('wc3_object_name') == child.name and a.get('wc3_sequence_name') == setAnimationName:
                    child_act = a
                    break
            if not child_act:
                child_act = bpy.data.actions.get(f"{setAnimationName} {child.name}")
            if not child_act and target_action_name:
                child_act = bpy.data.actions.get(f"{target_action_name} {child.name}")
            if child_act:
                if child.animation_data is None:
                    child.animation_data_create()
                child.animation_data.action = child_act


def set_team_color_property(self, context):
    self.teamColor = constants.TEAM_COLORS[self.setTeamColor]


def set_bone_node_type(self, context):
    bone = getattr(context, 'active_bone', None) or getattr(context, 'bone', None)
    if bone is None and getattr(context, 'active_pose_bone', None):
        bone = context.active_pose_bone.bone
    if bone and hasattr(bone, 'warcraft_3'):
        nodeType = bone.warcraft_3.nodeType
        if not nodeType:
            return
        obj = context.object
        if obj and obj.type == 'ARMATURE':
            collection_name = nodeType.lower() + 's'
            bone_collection = obj.data.collections.get(collection_name)
            
            if not bone_collection:
                if nodeType in {'BONE', 'ATTACHMENT', 'COLLISION_SHAPE', 'EVENT', 'HELPER', 'EMITTER', 'RIBBON'}:
                    bone_collection = obj.data.collections.new(collection_name)
            
            if bone_collection:
                if hasattr(bone, "bone"): # PoseBone
                    bone_collection.assign(bone.bone)
                else: # Bone or EditBone
                    bone_collection.assign(bone)
