@tool
class_name MdxBuilder
extends RefCounted

const BlpParser = preload("blp_parser.gd")

## Builds a complete Godot 4 Node3D scene from parsed MDX data.
## Supports Skeleton3D, ArrayMesh, StandardMaterial3D (with Additive blending),
## AnimationPlayer, and GPUParticles3D.

static func build_scene(model: Dictionary, mdx_file_path: String = "", options: Dictionary = {}) -> Node3D:
	var global_scale = float(options.get("scale", 0.03))
	var import_particles = bool(options.get("import_particles", true))
	var import_animations = bool(options.get("import_animations", true))
	var team_color = options.get("team_color", Color(1.0, 0.0, 0.0, 1.0))

	var root = Node3D.new()
	root.name = model.get("name", "WarCraft3Model")
	if root.name.is_empty():
		root.name = "WarCraft3Model"

	# 1. Coordinate Helpers (WC3 Z-up -> Godot Y-up)
	var conv_pos = func(v: Vector3) -> Vector3:
		return Vector3(v.x, v.z, -v.y) * global_scale

	var conv_rot = func(q: Quaternion) -> Quaternion:
		# WC3 quat (x, y, z, w) -> Godot (x, z, -y, w)
		return Quaternion(q.x, q.z, -q.y, q.w).normalized()

	var conv_scale = func(s: Vector3) -> Vector3:
		return Vector3(s.x, s.z, s.y)

	# 2. Build Textures & Materials
	var materials = _build_materials(model, mdx_file_path, team_color)

	# 3. Build Skeleton3D
	var skeleton = Skeleton3D.new()
	skeleton.name = "Skeleton3D"
	root.add_child(skeleton)
	skeleton.owner = root

	var obj_id_to_bone: Dictionary = {}
	var all_nodes = model.get("all_nodes", [])
	var pivot_points = model.get("pivot_points", [])
	var used_bone_names: Dictionary = {}

	for node in all_nodes:
		var bone_name = node.get("name", "Bone")
		bone_name = bone_name.replace(":", "_").replace("/", "_").strip_edges()
		if bone_name.is_empty():
			bone_name = "Node_" + str(node.get("object_id", 0))

		if bone_name in used_bone_names:
			used_bone_names[bone_name] += 1
			bone_name = bone_name + "_" + str(used_bone_names[bone_name])
		else:
			used_bone_names[bone_name] = 0

		var b_idx = skeleton.add_bone(bone_name)
		obj_id_to_bone[node.get("object_id", -1)] = b_idx

	# Set parent hierarchy & rest transforms
	for node in all_nodes:
		var b_idx = obj_id_to_bone.get(node.get("object_id", -1), -1)
		if b_idx < 0:
			continue
		var p_id = node.get("parent_id", 0xffffffff)
		var p_idx = obj_id_to_bone.get(p_id, -1)
		if p_idx >= 0 and p_idx != b_idx:
			skeleton.set_bone_parent(b_idx, p_idx)

		var obj_id = node.get("object_id", 0)
		var pivot = pivot_points[obj_id] if obj_id < pivot_points.size() else Vector3.ZERO
		var local_rest = Vector3.ZERO
		if p_idx >= 0 and p_id < pivot_points.size():
			var p_pivot = pivot_points[p_id]
			local_rest = conv_pos.call(pivot - p_pivot)
		else:
			local_rest = conv_pos.call(pivot)

		skeleton.set_bone_rest(b_idx, Transform3D(Basis(), local_rest))

	# 4. Build Meshes (ArrayMesh per Geoset)
	var geosets = model.get("geosets", [])
	for g_idx in range(geosets.size()):
		var geoset = geosets[g_idx]
		var v_count = geoset.vertices.size()
		if v_count == 0 or geoset.indices.size() == 0:
			continue

		var arrays = []
		arrays.resize(Mesh.ARRAY_MAX)

		var out_verts = PackedVector3Array()
		out_verts.resize(v_count)
		for v in range(v_count):
			out_verts[v] = conv_pos.call(geoset.vertices[v])
		arrays[Mesh.ARRAY_VERTEX] = out_verts

		if geoset.normals.size() == v_count:
			var out_norms = PackedVector3Array()
			out_norms.resize(v_count)
			for n in range(v_count):
				var norm = geoset.normals[n]
				out_norms[n] = Vector3(norm.x, norm.z, -norm.y).normalized()
			arrays[Mesh.ARRAY_NORMAL] = out_norms

		if geoset.uvs.size() == v_count:
			arrays[Mesh.ARRAY_TEX_UV] = geoset.uvs

		arrays[Mesh.ARRAY_INDEX] = geoset.indices

		# Skinning weights (ARRAY_BONES & ARRAY_WEIGHTS)
		var out_bones = PackedInt32Array()
		out_bones.resize(v_count * 4)
		var out_weights = PackedFloat32Array()
		out_weights.resize(v_count * 4)

		for v in range(v_count):
			var groups = geoset.vertex_groups[v] if v < geoset.vertex_groups.size() else []
			var base = v * 4
			if groups.size() > 0:
				var w = 1.0 / float(min(groups.size(), 4))
				for bi in range(4):
					if bi < groups.size():
						var raw_id = groups[bi]
						var mapped_bone = obj_id_to_bone.get(raw_id, 0)
						out_bones[base + bi] = mapped_bone
						out_weights[base + bi] = w
					else:
						out_bones[base + bi] = 0
						out_weights[base + bi] = 0.0
			else:
				out_bones[base + 0] = 0
				out_weights[base + 0] = 1.0

		arrays[Mesh.ARRAY_BONES] = out_bones
		arrays[Mesh.ARRAY_WEIGHTS] = out_weights

		var arr_mesh = ArrayMesh.new()
		arr_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)

		var mesh_inst = MeshInstance3D.new()
		mesh_inst.name = root.name + "_" + str(g_idx)
		mesh_inst.mesh = arr_mesh
		mesh_inst.skeleton = NodePath("../Skeleton3D")

		var mat_id = geoset.get("material_id", 0)
		if mat_id < materials.size() and materials[mat_id]:
			mesh_inst.set_surface_override_material(0, materials[mat_id])

		# Geoset animation tint & alpha
		var ga = _find_geoset_anim(model, g_idx)
		if ga:
			var mat = materials[mat_id] if mat_id < materials.size() else null
			if mat and mat is StandardMaterial3D:
				var c = ga.get("color", Vector3(1, 1, 1))
				var a = ga.get("alpha", 1.0)
				if c != Vector3(1, 1, 1) or a < 0.99:
					var dup_mat = mat.duplicate()
					dup_mat.albedo_color = Color(c.x, c.y, c.z, a)
					mesh_inst.set_surface_override_material(0, dup_mat)

		root.add_child(mesh_inst)
		mesh_inst.owner = root

	# 5. Build AnimationPlayer
	if import_animations and model.sequences.size() > 0:
		_build_animations(model, root, skeleton, obj_id_to_bone, conv_pos, conv_rot, conv_scale)

	# 6. Build Particle Emitters (PRE2)
	if import_particles:
		_build_particles(model, root, skeleton, obj_id_to_bone, materials, global_scale)

	return root


static func _find_geoset_anim(model: Dictionary, geoset_idx: int) -> Dictionary:
	for ga in model.get("geoset_animations", []):
		if ga.get("geoset_id", -1) == geoset_idx:
			return ga
	return {}


static func _build_materials(model: Dictionary, mdx_file_path: String, team_color: Color) -> Array[Material]:
	var materials: Array[Material] = []
	var textures = model.get("textures", [])
	var dir = mdx_file_path.get_base_dir() if not mdx_file_path.is_empty() else ""

	for m_idx in range(model.materials.size()):
		var mat_def = model.materials[m_idx]
		var layers = mat_def.get("layers", [])
		if layers.is_empty():
			materials.append(StandardMaterial3D.new())
			continue

		var layer0 = layers[0]
		var filter_mode = int(layer0.get("filter_mode", 0))
		var shading_flags = int(layer0.get("shading_flags", 0))
		var tex_id = int(layer0.get("texture_id", 0))
		var alpha = float(layer0.get("alpha", 1.0))

		var mat = StandardMaterial3D.new()
		mat.resource_name = "WC3_Mat_" + str(m_idx)

		# Shading & Blend Modes
		var is_two_sided = (shading_flags & 0x10) != 0 or (shading_flags & 0x8) != 0
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED if is_two_sided else BaseMaterial3D.CULL_BACK

		var is_unshaded = (shading_flags & 0x1) != 0
		if is_unshaded:
			mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED

		match filter_mode:
			0: # Opaque
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
				mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
			1: # Transparent / Cutout
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				mat.alpha_scissor_threshold = 0.5
			2: # Alpha Blend
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			3, 4: # Additive / AddAlpha
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
				mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			5, 6: # Modulate
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_MUL
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA

		if alpha < 0.99:
			mat.albedo_color = Color(1.0, 1.0, 1.0, alpha)

		# Texture assignment
		if tex_id < textures.size():
			var tex_def = textures[tex_id]
			var tex = _load_texture(tex_def, dir, team_color)
			if tex:
				mat.albedo_texture = tex
				if filter_mode in [3, 4]:
					mat.emission_enabled = true
					mat.emission_texture = tex
					mat.emission = Color(1.0, 1.0, 1.0)
					mat.emission_energy_multiplier = 1.0

		materials.append(mat)
	return materials


static func _load_texture(tex_def: Dictionary, base_dir: String, team_color: Color) -> Texture2D:
	var rep_id = int(tex_def.get("replaceable_id", 0))
	if rep_id == 1:
		# Team Color
		var img = Image.create(32, 32, false, Image.FORMAT_RGBA8)
		img.fill(team_color)
		return ImageTexture.create_from_image(img)
	elif rep_id == 2:
		# Team Glow
		var img = Image.create(32, 32, false, Image.FORMAT_RGBA8)
		img.fill(Color(team_color.r, team_color.g, team_color.b, 0.75))
		return ImageTexture.create_from_image(img)

	var rel_path = str(tex_def.get("path", "")).strip_edges()
	if rel_path.is_empty():
		return null

	var base_stem = rel_path.get_file().get_basename()
	var search_candidates = [
		base_dir + "/" + base_stem + ".png",
		base_dir + "/" + base_stem + ".jpg",
		base_dir + "/" + base_stem + ".webp",
		base_dir + "/Textures/" + base_stem + ".png",
		base_dir + "/Textures/" + base_stem + ".jpg",
		base_dir + "/" + rel_path,
		base_dir + "/" + rel_path.get_file(),
		base_dir + "/Textures/" + rel_path.get_file(),
		base_dir + "/" + base_stem + ".blp"
	]

	for cand in search_candidates:
		if FileAccess.file_exists(cand):
			var ext = cand.get_extension().to_lower()
			if ext in ["png", "jpg", "jpeg", "webp"]:
				var img = Image.load_from_file(cand)
				if img:
					return ImageTexture.create_from_image(img)
			elif ext == "blp":
				var blp_img = BlpParser.load_from_file(cand)
				if blp_img:
					return ImageTexture.create_from_image(blp_img)

	return null


static func _build_animations(model: Dictionary, root: Node, skeleton: Skeleton3D, obj_id_to_bone: Dictionary, conv_pos: Callable, conv_rot: Callable, conv_scale: Callable) -> void:
	var anim_player = AnimationPlayer.new()
	anim_player.name = "AnimationPlayer"
	root.add_child(anim_player)
	anim_player.owner = root

	var lib = AnimationLibrary.new()

	for seq in model.sequences:
		var seq_name = seq.name
		var start_time = float(seq.start)
		var end_time = float(seq.end)
		var duration = max((end_time - start_time) / 1000.0, 0.05)

		var anim = Animation.new()
		anim.length = duration
		anim.loop_mode = Animation.LOOP_NONE if seq.non_looping else Animation.LOOP_LINEAR

		# Collect animated tracks from nodes
		for node in model.all_nodes:
			var b_idx = obj_id_to_bone.get(node.get("object_id", -1), -1)
			if b_idx < 0:
				continue
			var bone_name = skeleton.get_bone_name(b_idx)
			var track_prefix = "Skeleton3D:" + bone_name

			# Rotation tracks
			var r_tracks = node.get("rotation_tracks", [])
			var seq_r = r_tracks.filter(func(k): return k.time >= start_time and k.time <= end_time)
			if seq_r.size() > 0:
				var t_idx = anim.add_track(Animation.TYPE_ROTATION_3D)
				anim.track_set_path(t_idx, NodePath(track_prefix))
				for k in seq_r:
					var t = (float(k.time) - start_time) / 1000.0
					anim.rotation_track_insert_key(t_idx, t, conv_rot.call(k.value))

			# Translation tracks
			var t_tracks = node.get("translation_tracks", [])
			var seq_t = t_tracks.filter(func(k): return k.time >= start_time and k.time <= end_time)
			if seq_t.size() > 0:
				var t_idx = anim.add_track(Animation.TYPE_POSITION_3D)
				anim.track_set_path(t_idx, NodePath(track_prefix))
				var rest_pos = skeleton.get_bone_rest(b_idx).origin
				for k in seq_t:
					var t = (float(k.time) - start_time) / 1000.0
					anim.position_track_insert_key(t_idx, t, rest_pos + conv_pos.call(k.value))

			# Scale tracks
			var s_tracks = node.get("scale_tracks", [])
			var seq_s = s_tracks.filter(func(k): return k.time >= start_time and k.time <= end_time)
			if seq_s.size() > 0:
				var t_idx = anim.add_track(Animation.TYPE_SCALE_3D)
				anim.track_set_path(t_idx, NodePath(track_prefix))
				for k in seq_s:
					var t = (float(k.time) - start_time) / 1000.0
					anim.scale_track_insert_key(t_idx, t, conv_scale.call(k.value))

		lib.add_animation(seq_name, anim)

	anim_player.add_animation_library("", lib)


static func _build_particles(model: Dictionary, root: Node, skeleton: Skeleton3D, obj_id_to_bone: Dictionary, materials: Array[Material], global_scale: float) -> void:
	var emitters = model.get("particle_emitters_2", [])
	if emitters.is_empty():
		return

	for e_idx in range(emitters.size()):
		var em = emitters[e_idx]
		var obj_id = em.get("object_id", -1)
		var b_idx = obj_id_to_bone.get(obj_id, -1)
		if b_idx < 0:
			var p_id = em.get("parent_id", -1)
			b_idx = obj_id_to_bone.get(p_id, -1)

		var parent_node: Node = root
		if b_idx >= 0:
			var bone_name = skeleton.get_bone_name(b_idx)
			var attach = BoneAttachment3D.new()
			attach.name = "Attach_" + bone_name + "_" + str(e_idx)
			attach.bone_name = bone_name
			skeleton.add_child(attach)
			attach.owner = root
			parent_node = attach

		var p = GPUParticles3D.new()
		p.name = "W3_Particles_" + str(e_idx)

		var rate = float(em.get("emission_rate", 20.0))
		var life = float(em.get("life_span", 1.0))
		var speed = float(em.get("speed", 1.0)) * global_scale
		var variation = float(em.get("variation", 0.2))
		var gravity = float(em.get("gravity", 0.0)) * global_scale
		var width = float(em.get("width", 0.5)) * global_scale
		var length = float(em.get("length", 0.5)) * global_scale
		var filter_mode = int(em.get("filter_mode", 0))

		p.amount = int(clamp(rate * life * 2.0, 8, 250))
		p.lifetime = max(life, 0.1)
		p.randomness = clamp(variation, 0.0, 1.0)

		var p_mat = ParticleProcessMaterial.new()
		p_mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_POINT
		p_mat.direction = Vector3(0, 1, 0)
		p_mat.spread = float(em.get("cone_angle", 0.0)) * 57.3
		p_mat.initial_velocity_min = max(speed * (1.0 - variation), 0.05)
		p_mat.initial_velocity_max = max(speed * (1.0 + variation), 0.1)
		p_mat.gravity = Vector3(0, -gravity, 0)

		# 3-segment color ramp
		var colors = em.get("colors", [])
		if colors.size() >= 3:
			var grad = Gradient.new()
			grad.set_color(0, colors[0])
			grad.set_color(1, colors[2])
			var t_mid = clamp(float(em.get("time_middle", 0.5)), 0.05, 0.95)
			grad.add_point(t_mid, colors[1])
			var g_tex = GradientTexture1D.new()
			g_tex.gradient = grad
			p_mat.color_ramp = g_tex

		p.process_material = p_mat

		var quad = QuadMesh.new()
		quad.size = Vector2(max(width, 0.1), max(length, 0.1))

		var q_mat = StandardMaterial3D.new()
		q_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		q_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		q_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		if filter_mode == 1:
			q_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		else:
			q_mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
		q_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		q_mat.vertex_color_use_as_albedo = true

		var tex_id = int(em.get("texture_id", -1))
		if tex_id >= 0 and tex_id < materials.size() and materials[tex_id] is StandardMaterial3D:
			q_mat.albedo_texture = (materials[tex_id] as StandardMaterial3D).albedo_texture

		quad.material = q_mat
		p.draw_pass_1 = quad

		parent_node.add_child(p)
		p.owner = root
