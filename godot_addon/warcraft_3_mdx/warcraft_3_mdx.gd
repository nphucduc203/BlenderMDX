@tool
class_name Warcraft3MdxPlugin
extends EditorPlugin

const MdxImportPlugin = preload("mdx_importer.gd")
const BlpImportPlugin = preload("blp_importer.gd")

## WarCraft 3 MDX & BLP Importer Plugin for Godot 4
## Integrates direct drag-and-drop import for .mdx 3D models and .blp textures.

var mdx_import_plugin: MdxImportPlugin
var blp_import_plugin: BlpImportPlugin


func _enter_tree() -> void:
	mdx_import_plugin = MdxImportPlugin.new()
	add_import_plugin(mdx_import_plugin)

	blp_import_plugin = BlpImportPlugin.new()
	add_import_plugin(blp_import_plugin)

	print("[WarCraft 3] MDX and BLP Importers registered in Godot!")


func _exit_tree() -> void:
	if mdx_import_plugin:
		remove_import_plugin(mdx_import_plugin)
		mdx_import_plugin = null

	if blp_import_plugin:
		remove_import_plugin(blp_import_plugin)
		blp_import_plugin = null

	print("[WarCraft 3] MDX and BLP Importers unregistered.")
