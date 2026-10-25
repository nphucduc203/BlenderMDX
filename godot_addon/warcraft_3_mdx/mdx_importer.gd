@tool
class_name MdxImportPlugin
extends EditorImportPlugin

const MdxParser = preload("mdx_parser.gd")
const MdxBuilder = preload("mdx_builder.gd")

## Godot 4 EditorImportPlugin for WarCraft 3 (.mdx) models.

func _get_importer_name() -> String:
	return "warcraft3.mdx"


func _get_visible_name() -> String:
	return "WarCraft 3 MDX Model"


func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["mdx"])


func _get_save_extension() -> String:
	return "scn"


func _get_resource_type() -> String:
	return "PackedScene"


func _get_preset_count() -> int:
	return 1


func _get_preset_name(preset_index: int) -> String:
	return "Default"


func _get_import_order() -> int:
	return 100


func _get_priority() -> float:
	return 1.0


func _get_import_options(path: String, preset_index: int) -> Array[Dictionary]:
	return [
		{
			"name": "scale",
			"default_value": 0.03,
			"property_hint": PROPERTY_HINT_RANGE,
			"hint_string": "0.001,1.0,0.001"
		},
		{
			"name": "import_particles",
			"default_value": true
		},
		{
			"name": "import_animations",
			"default_value": true
		},
		{
			"name": "team_color",
			"default_value": Color(1.0, 0.0, 0.0, 1.0)
		}
	]


func _get_option_visibility(path: String, option_name: StringName, options: Dictionary) -> bool:
	return true


func _import(source_file: String, save_path: String, options: Dictionary, platform_variants: Array[String], gen_files: Array[String]) -> Error:
	var model = MdxParser.parse_file(source_file)
	if model.is_empty():
		return ERR_PARSE_ERROR

	var scene_root = MdxBuilder.build_scene(model, source_file, options)
	if not scene_root:
		return ERR_CANT_CREATE

	var packed_scene = PackedScene.new()
	var pack_err = packed_scene.pack(scene_root)
	if pack_err != OK:
		scene_root.queue_free()
		return pack_err

	var filename = save_path + "." + _get_save_extension()
	var save_err = ResourceSaver.save(packed_scene, filename)
	scene_root.queue_free()

	return save_err
