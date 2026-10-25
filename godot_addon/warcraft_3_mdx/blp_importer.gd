@tool
class_name BlpImportPlugin
extends EditorImportPlugin

const BlpParser = preload("blp_parser.gd")

## Godot 4 EditorImportPlugin for WarCraft 3 (.blp) textures.

func _get_importer_name() -> String:
	return "warcraft3.blp"


func _get_visible_name() -> String:
	return "WarCraft 3 BLP Texture"


func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["blp"])


func _get_save_extension() -> String:
	return "ctex"


func _get_resource_type() -> String:
	return "CompressedTexture2D"


func _get_preset_count() -> int:
	return 1


func _get_preset_name(preset_index: int) -> String:
	return "Default"


func _get_import_order() -> int:
	return 50


func _get_priority() -> float:
	return 1.0


func _get_import_options(path: String, preset_index: int) -> Array[Dictionary]:
	return []


func _get_option_visibility(path: String, option_name: StringName, options: Dictionary) -> bool:
	return true


func _import(source_file: String, save_path: String, options: Dictionary, platform_variants: Array[String], gen_files: Array[String]) -> Error:
	var image = BlpParser.load_from_file(source_file)
	if not image:
		# Fallback: check if converted .png exists next to it
		var png_path = source_file.get_basename() + ".png"
		if FileAccess.file_exists(png_path):
			image = Image.load_from_file(png_path)
		else:
			return ERR_PARSE_ERROR

	return image.save_png(save_path + ".png")
