@tool
class_name MdxParser
extends RefCounted

## WarCraft 3 (.mdx) Binary Parser for Godot 4
## Reads standard Warcraft III TFT (version 800) and Reforged (version 1000) models.

static func parse_file(path: String) -> Dictionary:
	var f = FileAccess.open(path, FileAccess.READ)
	if not f:
		push_error("[MdxParser] Cannot open file: " + path)
		return {}

	var magic = f.get_buffer(4).get_string_from_ascii()
	if magic != "MDLX":
		push_error("[MdxParser] Not a valid MDX file (invalid magic: " + magic + ")")
		return {}

	var model = {
		"name": "",
		"version": 800,
		"geosets": [],
		"materials": [],
		"textures": [],
		"sequences": [],
		"global_sequences": [],
		"bones": [],
		"helpers": [],
		"attachments": [],
		"pivot_points": [],
		"particle_emitters_2": [],
		"geoset_animations": [],
		"cameras": [],
		"all_nodes": [] # nodes indexed by object_id
	}

	var file_length = f.get_length()
	while f.get_position() < file_length:
		var chunk_id = f.get_buffer(4).get_string_from_ascii()
		var chunk_size = f.get_32()
		var chunk_end = f.get_position() + chunk_size

		match chunk_id:
			"VERS":
				model.version = f.get_32()
			"MODL":
				_parse_modl(f, chunk_end, model)
			"SEQS":
				_parse_seqs(f, chunk_end, model)
			"GLBS":
				_parse_glbs(f, chunk_end, model)
			"MTLS":
				_parse_mtls(f, chunk_end, model)
			"TEXS":
				_parse_texs(f, chunk_end, model)
			"GEOS":
				_parse_geos(f, chunk_end, model)
			"GEOA":
				_parse_geoa(f, chunk_end, model)
			"BONE":
				_parse_bone(f, chunk_end, model)
			"HELP":
				_parse_help(f, chunk_end, model)
			"ATCH":
				_parse_atch(f, chunk_end, model)
			"PIVT":
				_parse_pivt(f, chunk_end, model)
			"PRE2":
				_parse_pre2(f, chunk_end, model)
			"CAMS":
				_parse_cams(f, chunk_end, model)
			_:
				# Skip unhandled chunk
				pass

		f.seek(chunk_end)

	_index_nodes(model)
	return model


static func _get_fixed_string(f: FileAccess, length: int) -> String:
	var buf = f.get_buffer(length)
	var null_pos = buf.find(0)
	if null_pos >= 0:
		buf = buf.slice(0, null_pos)
	var clean = PackedByteArray()
	for b in buf:
		if b >= 32 and b < 127:
			clean.append(b)
	return clean.get_string_from_ascii().strip_edges()


static func _parse_modl(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	model.name = _get_fixed_string(f, 80)
	var _anim_file = _get_fixed_string(f, 260)
	var _bounds_rad = f.get_float()
	var _min_x = f.get_float(); var _min_y = f.get_float(); var _min_z = f.get_float()
	var _max_x = f.get_float(); var _max_y = f.get_float(); var _max_z = f.get_float()
	if f.get_position() < chunk_end:
		var _blend_time = f.get_32()


static func _parse_seqs(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	var count = (chunk_end - f.get_position()) / 132
	for i in range(count):
		var seq = {
			"name": _get_fixed_string(f, 80),
			"start": f.get_32(),
			"end": f.get_32(),
			"move_speed": f.get_float(),
			"non_looping": f.get_32() != 0,
			"rarity": f.get_float(),
			"sync_point": f.get_32()
		}
		f.seek(f.get_position() + 28) # bounds radius (float) + extents (6 floats)
		model.sequences.append(seq)


static func _parse_glbs(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		model.global_sequences.append(f.get_32())


static func _parse_texs(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var rep_id = f.get_32()
		var path = _get_fixed_string(f, 260)
		var flags = f.get_32()
		model.textures.append({
			"replaceable_id": rep_id,
			"path": path.replace("\\", "/"),
			"flags": flags
		})


static func _parse_mtls(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var mat_size = f.get_32()
		var mat_end = f.get_position() - 4 + mat_size
		var prio = f.get_32()
		var flags = f.get_32()

		var mat = {
			"priority_plane": prio,
			"flags": flags,
			"layers": []
		}

		if f.get_position() < mat_end:
			var tag = f.get_buffer(4).get_string_from_ascii()
			if tag == "LAYS":
				var layer_count = f.get_32()
				for l in range(layer_count):
					var l_size = f.get_32()
					var l_end = f.get_position() - 4 + l_size
					var layer = {
						"filter_mode": f.get_32(),
						"shading_flags": f.get_32(),
						"texture_id": f.get_32(),
						"texture_animation_id": f.get_32(),
						"coord_id": f.get_32(),
						"alpha": f.get_float()
					}
					f.seek(l_end)
					mat.layers.append(layer)

		model.materials.append(mat)
		f.seek(mat_end)


static func _parse_geos(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var geos_size = f.get_32()
		var geos_end = f.get_position() - 4 + geos_size

		var geoset = {
			"vertices": PackedVector3Array(),
			"normals": PackedVector3Array(),
			"indices": PackedInt32Array(),
			"uvs": PackedVector2Array(),
			"vertex_groups": [],
			"material_id": 0
		}

		# VRTX
		if f.get_buffer(4).get_string_from_ascii() == "VRTX":
			var v_count = f.get_32()
			for v in range(v_count):
				geoset.vertices.append(Vector3(f.get_float(), f.get_float(), f.get_float()))

		# NRMS
		if f.get_buffer(4).get_string_from_ascii() == "NRMS":
			var n_count = f.get_32()
			for n in range(n_count):
				geoset.normals.append(Vector3(f.get_float(), f.get_float(), f.get_float()))

		# PTYP (primitive type)
		if f.get_buffer(4).get_string_from_ascii() == "PTYP":
			var p_count = f.get_32()
			f.seek(f.get_position() + p_count * 4)

		# PCNT (primitive count)
		if f.get_buffer(4).get_string_from_ascii() == "PCNT":
			var pc_count = f.get_32()
			f.seek(f.get_position() + pc_count * 4)

		# PVTX (indices)
		if f.get_buffer(4).get_string_from_ascii() == "PVTX":
			var idx_count = f.get_32()
			for i in range(idx_count):
				geoset.indices.append(f.get_16())

		# GNDX (vertex groups)
		var gndx: Array[int] = []
		if f.get_buffer(4).get_string_from_ascii() == "GNDX":
			var g_count = f.get_32()
			for g in range(g_count):
				gndx.append(f.get_8())

		# MTGC (matrix group counts)
		var mtgc: Array[int] = []
		if f.get_buffer(4).get_string_from_ascii() == "MTGC":
			var m_count = f.get_32()
			for m in range(m_count):
				mtgc.append(f.get_32())

		# MATS (matrix group indices)
		var mats: Array[int] = []
		if f.get_buffer(4).get_string_from_ascii() == "MATS":
			var mat_count = f.get_32()
			for m in range(mat_count):
				mats.append(f.get_32())

		# Reconstruct vertex bone attachments
		var matrix_groups = []
		var m_offset = 0
		for count in mtgc:
			matrix_groups.append(mats.slice(m_offset, m_offset + count))
			m_offset += count

		for group_idx in gndx:
			if group_idx < matrix_groups.size():
				geoset.vertex_groups.append(matrix_groups[group_idx])
			else:
				geoset.vertex_groups.append([])

		geoset.material_id = f.get_32()
		var _selection_group = f.get_32()
		var _selection_flags = f.get_32()
		f.seek(f.get_position() + 28) # bounds radius (float) + extents (6 floats)

		# Animation extents
		var anim_ext_count = f.get_32()
		f.seek(f.get_position() + anim_ext_count * 28)

		# UVAS
		if f.get_buffer(4).get_string_from_ascii() == "UVAS":
			var uvas_count = f.get_32()
			if uvas_count > 0:
				if f.get_buffer(4).get_string_from_ascii() == "UVBS":
					var uv_count = f.get_32()
					for u in range(uv_count):
						geoset.uvs.append(Vector2(f.get_float(), f.get_float()))
				# Skip secondary UV sets if present
				for extra in range(uvas_count - 1):
					if f.get_buffer(4).get_string_from_ascii() == "UVBS":
						var extra_uv = f.get_32()
						f.seek(f.get_position() + extra_uv * 8)

		model.geosets.append(geoset)
		f.seek(geos_end)


static func _parse_geoa(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var size = f.get_32()
		var end_pos = f.get_position() - 4 + size
		var ga = {
			"alpha": f.get_float(),
			"flags": f.get_32(),
			"color": Vector3(f.get_float(), f.get_float(), f.get_float()),
			"geoset_id": f.get_32()
		}
		model.geoset_animations.append(ga)
		f.seek(end_pos)


static func _parse_node_header(f: FileAccess) -> Dictionary:
	var inclusive_size = f.get_32()
	var end_pos = f.get_position() - 4 + inclusive_size
	var node = {
		"name": _get_fixed_string(f, 80),
		"object_id": f.get_32(),
		"parent_id": f.get_32(),
		"flags": f.get_32(),
		"translation_tracks": [],
		"rotation_tracks": [],
		"scale_tracks": []
	}

	while f.get_position() < end_pos:
		var track_tag = f.get_buffer(4).get_string_from_ascii()
		match track_tag:
			"KGTR":
				node.translation_tracks = _parse_tracks_vector3(f)
			"KGRT":
				node.rotation_tracks = _parse_tracks_quaternion(f)
			"KGSC":
				node.scale_tracks = _parse_tracks_vector3(f)
			_:
				# Unknown track tag; exit track loop
				f.seek(end_pos)
				break

	f.seek(end_pos)
	return node


static func _parse_tracks_vector3(f: FileAccess) -> Array:
	var count = f.get_32()
	var interp = f.get_32()
	var _global_seq = f.get_32()
	var tracks = []
	for i in range(count):
		var time = f.get_32()
		var val = Vector3(f.get_float(), f.get_float(), f.get_float())
		if interp > 1:
			var _in_tan = Vector3(f.get_float(), f.get_float(), f.get_float())
			var _out_tan = Vector3(f.get_float(), f.get_float(), f.get_float())
		tracks.append({"time": time, "value": val, "interp": interp})
	return tracks


static func _parse_tracks_quaternion(f: FileAccess) -> Array:
	var count = f.get_32()
	var interp = f.get_32()
	var _global_seq = f.get_32()
	var tracks = []
	for i in range(count):
		var time = f.get_32()
		# WC3 stores Quat as (x, y, z, w)
		var q = Quaternion(f.get_float(), f.get_float(), f.get_float(), f.get_float())
		if interp > 1:
			var _in_tan = Quaternion(f.get_float(), f.get_float(), f.get_float(), f.get_float())
			var _out_tan = Quaternion(f.get_float(), f.get_float(), f.get_float(), f.get_float())
		tracks.append({"time": time, "value": q, "interp": interp})
	return tracks


static func _parse_bone(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var node = _parse_node_header(f)
		var geoset_id = f.get_32()
		var _geoset_anim_id = f.get_32()
		node["type"] = "BONE"
		node["geoset_id"] = geoset_id
		model.bones.append(node)


static func _parse_help(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var node = _parse_node_header(f)
		node["type"] = "HELP"
		model.helpers.append(node)


static func _parse_atch(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var node = _parse_node_header(f)
		var _path = _get_fixed_string(f, 260)
		var _attachment_id = f.get_32()
		node["type"] = "ATCH"
		model.attachments.append(node)


static func _parse_pivt(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		model.pivot_points.append(Vector3(f.get_float(), f.get_float(), f.get_float()))


static func _parse_pre2(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var start_pos = f.get_position()
		var inclusive_size = f.get_32()
		var end_pos = start_pos + inclusive_size

		var node = _parse_node_header(f)
		node["type"] = "PRE2"

		node["speed"] = f.get_float()
		node["variation"] = f.get_float()
		node["cone_angle"] = f.get_float()
		node["gravity"] = f.get_float()
		node["life_span"] = f.get_float()
		node["emission_rate"] = f.get_float()
		node["width"] = f.get_float()
		node["length"] = f.get_float()
		node["filter_mode"] = f.get_32()
		node["rows"] = f.get_32()
		node["columns"] = f.get_32()
		node["head_or_tail"] = f.get_32()
		node["tail_length"] = f.get_float()
		node["time_middle"] = f.get_float()

		node["colors"] = [
			Color(f.get_float(), f.get_float(), f.get_float(), 1.0),
			Color(f.get_float(), f.get_float(), f.get_float(), 1.0),
			Color(f.get_float(), f.get_float(), f.get_float(), 1.0)
		]
		var a0 = f.get_8() / 255.0; var a1 = f.get_8() / 255.0; var a2 = f.get_8() / 255.0
		node["colors"][0].a = a0
		node["colors"][1].a = a1
		node["colors"][2].a = a2

		f.seek(f.get_position() + 12 + 48) # segment scaling (12) + UV intervals (48)
		node["texture_id"] = f.get_32()

		model.particle_emitters_2.append(node)
		f.seek(end_pos)


static func _parse_cams(f: FileAccess, chunk_end: int, model: Dictionary) -> void:
	while f.get_position() < chunk_end:
		var inclusive_size = f.get_32()
		var end_pos = f.get_position() - 4 + inclusive_size
		var cam = {
			"name": _get_fixed_string(f, 80),
			"position": Vector3(f.get_float(), f.get_float(), f.get_float()),
			"fov": f.get_float(),
			"far": f.get_float(),
			"near": f.get_float(),
			"target": Vector3(f.get_float(), f.get_float(), f.get_float())
		}
		model.cameras.append(cam)
		f.seek(end_pos)


static func _index_nodes(model: Dictionary) -> void:
	# Combine all nodes (bones, helpers, emitters, attachments) sorted by object_id
	var all = []
	all.append_array(model.bones)
	all.append_array(model.helpers)
	all.append_array(model.attachments)
	all.append_array(model.particle_emitters_2)
	all.sort_custom(func(a, b): return a.get("object_id", 0) < b.get("object_id", 0))
	model.all_nodes = all
