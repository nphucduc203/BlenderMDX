@tool
extends EditorScenePostImport

## WarCraft 3 Model Post-Import Processor for Godot 4
##
## How to use:
## 1. Copy this script (wc3_post_import.gd) into your Godot project.
## 2. In Godot FileSystem dock, select your exported WarCraft 3 (.glb) file.
## 3. In the Import dock (top left), look for "Import Script" -> "Custom Script".
## 4. Select this script (res://wc3_post_import.gd) and click "Reimport".
##
## What it does automatically:
## - Restores true Additive Blending (BLEND_MODE_ADD + SHADING_MODE_UNSHADED)
##   for all WC3 glowing meshes (auras, splash veils, ribbons, star effects).
## - Re-creates GPUParticles3D emitters attached to the exact character bones
##   with original WC3 color ramps, speeds, lifetimes, and zero gravity.

func _post_import(scene: Node) -> Object:
	_process_node(scene, scene)
	return scene


func _process_node(node: Node, root: Node) -> void:
	# 1. MeshInstance3D / ImporterMeshInstance3D: Configure Additive and Unshaded Materials
	if node is MeshInstance3D or node.get_class() == "ImporterMeshInstance3D":
		_process_mesh_materials(node)

	# 2. Emitter marker: Spawn GPUParticles3D with WC3 particle parameters
	var extras = _get_extras(node)
	if extras.get("wc3_type") == "emitter":
		_create_gpu_particles_from_emitter(node, extras, root)

	# 3. Recurse through children
	for child in node.get_children():
		_process_node(child, root)


func _get_extras(object: Object) -> Dictionary:
	if object and object.has_meta("extras"):
		var m = object.get_meta("extras")
		if m is Dictionary:
			return m
	return {}


func _process_mesh_materials(node: Node) -> void:
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
				# Adds pixel color directly to framebuffer with ZERO diffuse darkening
				mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
				mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA

				# Apply WC3 layer tint and exact layer alpha
				var tint = mat_extras.get("wc3_tint")
				if tint is Array and tint.size() >= 3:
					mat.albedo_color = Color(float(tint[0]), float(tint[1]), float(tint[2]), layer_alpha)
				else:
					mat.albedo_color = Color(1.0, 1.0, 1.0, layer_alpha)

				# In additive mode, emission multiplies radiant glow
				if mat.emission_enabled:
					mat.emission = Color(1.0, 1.0, 1.0)
					mat.emission_energy_multiplier = 1.0
			elif filter_mode == 1:
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				mat.alpha_scissor_threshold = 0.5
				if is_unshaded:
					mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			elif is_unshaded:
				mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
				mat.cull_mode = BaseMaterial3D.CULL_DISABLED


func _create_gpu_particles_from_emitter(emitter_node: Node, extras: Dictionary, root: Node) -> void:
	# Avoid duplicate creation on re-import
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

	particles.amount = int(clamp(rate * life * 2.0, 8, 250))
	particles.lifetime = max(life, 0.1)
	particles.explosiveness = 0.0
	particles.randomness = clamp(variation, 0.0, 1.0)

	# Particle Process Material
	var p_mat = ParticleProcessMaterial.new()
	p_mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_POINT
	p_mat.direction = Vector3(0, 1, 0)
	var cone_deg = float(extras.get("wc3_cone_angle", 0.0)) * 57.2958
	p_mat.spread = clamp(cone_deg, 0.0, 180.0)
	p_mat.initial_velocity_min = max(speed * (1.0 - variation), 0.05)
	p_mat.initial_velocity_max = max(speed * (1.0 + variation), 0.1)
	p_mat.gravity = Vector3(0, -gravity, 0)

	# 3-segment color / alpha gradient (Start -> Middle -> End)
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

	particles.process_material = p_mat

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

	quad.material = q_mat
	particles.draw_pass_1 = quad

	emitter_node.add_child(particles)
	particles.owner = root
