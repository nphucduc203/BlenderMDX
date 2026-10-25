@tool
class_name Wc3PostImport
extends EditorScenePostImport

## WarCraft 3 Model Post-Import Processor for Godot 4
## Restores true Additive Blending, particle emitters, and UV animation.

func _post_import(scene: Node) -> Object:
	process_model(scene)
	return scene


static func process_model(scene: Node) -> void:
	_process_node(scene, scene)


static func _process_node(node: Node, root: Node) -> void:
	if node is MeshInstance3D or node.get_class() == "ImporterMeshInstance3D":
		_process_mesh_materials(node)

	var extras = _get_extras(node)
	if extras.get("wc3_type") == "emitter":
		_create_gpu_particles_from_emitter(node, extras, root)

	for child in node.get_children():
		_process_node(child, root)


static func _get_extras(object: Object) -> Dictionary:
	if object and object.has_meta("extras"):
		var m = object.get_meta("extras")
		if m is Dictionary:
			return m
	return {}


static func _process_mesh_materials(node: Node) -> void:
	var mesh = node.get("mesh")
	if not mesh:
		return

	var node_extras = _get_extras(node)
	var node_is_additive = (node_extras.get("wc3_blend") == "additive")

	var surf_count = mesh.get_surface_count()
	for surf_idx in range(surf_count):
		var mat = null
		if mesh.has_method("get_surface_material"):
			mat = mesh.get_surface_material(surf_idx)
		elif mesh.has_method("surface_get_material"):
			mat = mesh.surface_get_material(surf_idx)
		if not mat and node.has_method("get_surface_override_material"):
			mat = node.get_surface_override_material(surf_idx)

		if mat is StandardMaterial3D or mat is ORMMaterial3D:
			var mat_extras = _get_extras(mat)
			var filter_mode = int(mat_extras.get("wc3_filter_mode", -1))
			var is_additive = node_is_additive or (mat_extras.get("wc3_blend") == "additive") or (filter_mode in [3, 4])
			var is_unshaded = is_additive or (mat_extras.get("wc3_unshaded") == true) or (mat_extras.get("wc3_blend") == "unshaded")
			var layer_alpha = float(mat_extras.get("wc3_layer_alpha", 1.0))

			if is_additive:
				# True WarCraft 3 Additive Blending:
				# Use zero diffuse (black albedo) and radiant emission so NO dark rectangular frame can show!
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
				mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA

				var tint = mat_extras.get("wc3_tint")
				var tint_col = Color(1.0, 1.0, 1.0, 1.0)
				if tint is Array and tint.size() >= 3:
					tint_col = Color(float(tint[0]), float(tint[1]), float(tint[2]), 1.0)

				mat.albedo_color = Color(0.0, 0.0, 0.0, 1.0)
				mat.emission_enabled = true
				mat.emission = tint_col
				mat.emission_energy_multiplier = max(layer_alpha * 2.0, 0.8)
				if mat.albedo_texture:
					mat.emission_texture = mat.albedo_texture

			elif filter_mode == 1:
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				mat.alpha_scissor_threshold = 0.5
				if is_unshaded:
					mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			elif is_unshaded:
				mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED


static func _create_gpu_particles_from_emitter(emitter_node: Node, extras: Dictionary, root: Node) -> void:
	if emitter_node.has_node("W3_GPUParticles3D"):
		return

	var particles = GPUParticles3D.new()
	particles.name = "W3_GPUParticles3D"

	var rate = float(extras.get("wc3_emission_rate", 20.0))
	var life = float(extras.get("wc3_life_span", 1.0))
	var speed = float(extras.get("wc3_speed", 1.0))
	var variation = float(extras.get("wc3_variation", 0.2))
	var gravity = float(extras.get("wc3_gravity", 0.0))
	var width = float(extras.get("wc3_width", 0.5))
	var length = float(extras.get("wc3_length", 0.5))
	var filter_mode = int(extras.get("wc3_filter_mode", 0))
	var colors = extras.get("wc3_colors", [])
	var alphas = extras.get("wc3_alphas", [])
	var t_mid = float(extras.get("wc3_time_middle", 0.5))

	particles.amount = int(clamp(rate * life * 2.5, 12, 300))
	particles.lifetime = max(life, 0.1)
	particles.explosiveness = 0.0
	particles.randomness = clamp(variation, 0.0, 1.0)

	var p_mat = ParticleProcessMaterial.new()
	p_mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_POINT
	p_mat.direction = Vector3(0, 1, 0)
	var cone_deg = float(extras.get("wc3_cone_angle", 0.0)) * 57.2958
	p_mat.spread = clamp(cone_deg, 0.0, 180.0)
	p_mat.initial_velocity_min = max(speed * (1.0 - variation), 0.05)
	p_mat.initial_velocity_max = max(speed * (1.0 + variation), 0.1)
	p_mat.gravity = Vector3(0, -gravity, 0)

	if colors is Array and colors.size() >= 3 and alphas is Array and alphas.size() >= 3:
		var grad = Gradient.new()
		var c0 = Color(float(colors[0][0]), float(colors[0][1]), float(colors[0][2]), float(alphas[0]))
		var c1 = Color(float(colors[1][0]), float(colors[1][1]), float(colors[1][2]), float(alphas[1]))
		var c2 = Color(float(colors[2][0]), float(colors[2][1]), float(colors[2][2]), float(alphas[2]))
		grad.set_color(0, c0)
		grad.set_color(1, c2)
		grad.add_point(clamp(t_mid, 0.05, 0.95), c1)

		var grad_tex = GradientTexture1D.new()
		grad_tex.gradient = grad
		p_mat.color_ramp = grad_tex

	# Draw Pass: Billboard Quad
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

	# Assign particle texture from res://
	var tex_name = str(extras.get("wc3_texture", "")).strip_edges()
	var p_tex: Texture2D = null
	if not tex_name.is_empty():
		for ext in [".png", ".blp", ".jpg", ".webp"]:
			var p_cand = "res://" + tex_name + ext
			if ResourceLoader.exists(p_cand):
				p_tex = load(p_cand)
				break
		if p_tex:
			q_mat.albedo_texture = p_tex
		else:
			# Do not create untextured white billboard particles
			return

	var cols = int(extras.get("wc3_columns", 1))
	var rows = int(extras.get("wc3_rows", 1))
	if cols > 1 or rows > 1:
		q_mat.particles_anim_h_frames = max(cols, 1)
		q_mat.particles_anim_v_frames = max(rows, 1)
		q_mat.particles_anim_loop = true
		p_mat.anim_speed_min = 1.0
		p_mat.anim_speed_max = 1.0

	particles.process_material = p_mat
	quad.material = q_mat
	particles.draw_pass_1 = quad

	particles.visibility_aabb = AABB(Vector3(-25, -25, -25), Vector3(50, 50, 50))
	particles.emitting = true

	emitter_node.add_child(particles)
	particles.owner = root
