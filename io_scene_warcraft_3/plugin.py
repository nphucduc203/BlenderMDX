import bpy
from . import operators
from . import preferences
from . import types
from . import ui


def menu_import_mdx(self, context):
    self.layout.operator(operators.WarCraft3OperatorImportMDX.bl_idname, text='WarCraft 3 (.mdx, .mdl)')


def menu_export_glb(self, context):
    self.layout.operator(operators.WarCraft3OperatorExportGLB.bl_idname, text='WarCraft 3 (.glb)')


def register_class_safe(cls):
    try:
        bpy.utils.register_class(cls)
    except ValueError:
        bpy.utils.unregister_class(cls)
        bpy.utils.register_class(cls)


def register():
    register_class_safe(preferences.WarCraft3Preferences)
    register_class_safe(operators.WarCraft3OperatorImportMDX)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_mdx)
    
    register_class_safe(operators.WarCraft3OperatorExportGLB)
    bpy.types.TOPBAR_MT_file_export.append(menu_export_glb)
    
    register_class_safe(operators.WarCraft3OperatorCleanBoneShapes)
    register_class_safe(operators.WarCraft3OperatorAddSequenceToArmature)
    register_class_safe(operators.WarCraft3OperatorRemoveSequenceToArmature)
    register_class_safe(operators.WarCraft3OperatorUpdateBoneSettings)
    register_class_safe(operators.WarCraft3OperatorPushToNLA)
    register_class_safe(operators.WarCraft3OperatorConvertParticles)
    register_class_safe(operators.WarCraft3OperatorToggleParticles)
    
    register_class_safe(types.WarCraft3ArmatureSequenceList)
    register_class_safe(types.WarCraft3ArmatureProperties)
    types.WarCraft3ArmatureProperties.bpy_type.warcraft_3 = bpy.props.PointerProperty(type=types.WarCraft3ArmatureProperties)
    register_class_safe(types.WarCraft3BoneProperties)
    types.WarCraft3BoneProperties.bpy_type.warcraft_3 = bpy.props.PointerProperty(type=types.WarCraft3BoneProperties)
    
    register_class_safe(ui.WARCRAFT3_PT_viewport)
    register_class_safe(ui.WARCRAFT3_PT_armature)
    register_class_safe(ui.WARCRAFT3_PT_bone)


def unregister():
    try:
        bpy.types.TOPBAR_MT_file_import.remove(menu_import_mdx)
    except Exception:
        pass
    try:
        bpy.types.TOPBAR_MT_file_export.remove(menu_export_glb)
    except Exception:
        pass
    for cls in (
        ui.WARCRAFT3_PT_bone,
        ui.WARCRAFT3_PT_armature,
        ui.WARCRAFT3_PT_viewport,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(types.WarCraft3BoneProperties.bpy_type, 'warcraft_3'):
        del types.WarCraft3BoneProperties.bpy_type.warcraft_3
    try:
        bpy.utils.unregister_class(types.WarCraft3BoneProperties)
    except Exception:
        pass
    if hasattr(types.WarCraft3ArmatureProperties.bpy_type, 'warcraft_3'):
        del types.WarCraft3ArmatureProperties.bpy_type.warcraft_3
    for cls in (
        types.WarCraft3ArmatureProperties,
        types.WarCraft3ArmatureSequenceList,
        operators.WarCraft3OperatorCleanBoneShapes,
        operators.WarCraft3OperatorExportGLB,
        operators.WarCraft3OperatorPushToNLA,
        operators.WarCraft3OperatorConvertParticles,
        operators.WarCraft3OperatorToggleParticles,
        operators.WarCraft3OperatorUpdateBoneSettings,
        operators.WarCraft3OperatorRemoveSequenceToArmature,
        operators.WarCraft3OperatorAddSequenceToArmature,
        operators.WarCraft3OperatorImportMDX,
        preferences.WarCraft3Preferences,
    ):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
