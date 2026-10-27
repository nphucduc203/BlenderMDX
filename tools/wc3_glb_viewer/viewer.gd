extends Node3D
# Standalone viewer for .glb files exported by the BlenderMDX addon.
# Open any exported model, cycle its sequences, orbit the camera. Nothing auto-quits.

const DEFAULT_MODEL := "res://wc3_export_test/2_95.glb"

var model: Node3D
var player: AnimationPlayer
var animations: PackedStringArray = PackedStringArray()
var animation_index := 0
var paused := false

var camera: Camera3D
var camera_target := Vector3(0, 0.9, 0)
var camera_yaw := deg_to_rad(28.0)
var camera_pitch := deg_to_rad(12.0)
var camera_distance := 6.0
var dragging := false

var status_label: Label
var anim_label: Label
var file_dialog: FileDialog


func _ready() -> void:
	_build_world()
	_build_ui()
	var wanted := _requested_path()
	if wanted != "" and FileAccess.file_exists(wanted):
		load_model(wanted)
	elif FileAccess.file_exists(DEFAULT_MODEL):
		load_model(DEFAULT_MODEL)
	else:
		file_dialog.popup_centered()


func _requested_path() -> String:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--model="):
			return arg.trim_prefix("--model=")
	return ""


func load_model(path: String) -> void:
	if model:
		model.queue_free()
		model = null
		player = null
	# Read the glTF directly instead of ResourceLoader: a freshly exported .glb has no
	# import cache yet (and files outside res:// never get one), so load() would fail.
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(path, state) != OK:
		_status("Cannot read %s (not a valid .glb/.gltf?)" % path)
		return
	model = doc.generate_scene(state) as Node3D
	if model == null:
		_status("%s has no 3D scene" % path)
		return
	add_child(model)
	player = _find_animation_player(model)
	animations = PackedStringArray()
	if player:
		animations = player.get_animation_list()
		for anim_name in animations:
			# glTF sequences arrive without a loop flag; cycle them so the viewer keeps moving.
			player.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
		if animations.size() > 0:
			player.play(animations[0])
		player.speed_scale = 1.0
	animation_index = 0
	# One frame first: skinned meshes report their rest bounds until the skeleton updates.
	await get_tree().process_frame
	_fit_camera()
	_status("%s | meshes %d | surfaces %d | animations %d | bones %d" % [
		path.get_file(), _count_meshes(model), _count_surfaces(model),
		animations.size(), _count_bones(model)])
	_show_animation()


func _fit_camera() -> void:
	# Skinned meshes report unreliable bounds on the first frames, so only trust a
	# measurement that is plausibly a model; otherwise use the WarCraft 3 framing.
	var bounds := _combined_aabb(model)
	var longest := bounds.get_longest_axis_size()
	if longest < 1.0 or longest > 100.0:
		camera_target = Vector3(0, 1.7, 0)
		camera_distance = 7.5
		return
	camera_target = bounds.get_center()
	camera_distance = clamp(longest * 1.9, 2.0, 60.0)


func _combined_aabb(node: Node) -> AABB:
	var result := AABB()
	var any := false
	var stack: Array = [node]
	while not stack.is_empty():
		var n = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
			# Instance-level AABB: it follows the skin, mesh.get_aabb() does not.
			var world := (n as Node3D).global_transform * (n as MeshInstance3D).get_aabb()
			result = result.merge(world) if any else world
			any = true
	return result


func _count_meshes(node: Node) -> int:
	return len(node.find_children("*", "MeshInstance3D", true, false))


func _count_surfaces(node: Node) -> int:
	var total := 0
	for m in node.find_children("*", "MeshInstance3D", true, false):
		if m.mesh != null:
			total += m.mesh.get_surface_count()
	return total


func _count_bones(node: Node) -> int:
	var skels := node.find_children("*", "Skeleton3D", true, false)
	return skels[0].get_bone_count() if skels.size() > 0 else 0


func _find_animation_player(node: Node) -> AnimationPlayer:
	var found := node.find_children("*", "AnimationPlayer", true, false)
	return found[0] if found.size() > 0 else null


func _show_animation() -> void:
	if animations.size() == 0:
		anim_label.text = "no animations"
		return
	anim_label.text = "%d/%d  %s" % [animation_index + 1, animations.size(), animations[animation_index]]


func _status(text: String) -> void:
	status_label.text = text


func next_animation(step: int) -> void:
	if animations.size() == 0:
		return
	animation_index = (animation_index + step) % animations.size()
	player.play(animations[animation_index])
	_show_animation()


func _toggle_pause() -> void:
	paused = not paused
	player.speed_scale = 0.0 if paused else 1.0


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_RIGHT, KEY_D:
				next_animation(1)
			KEY_LEFT, KEY_A:
				next_animation(-1)
			KEY_SPACE:
				_toggle_pause()
			KEY_O:
				file_dialog.popup_centered()
			KEY_F:
				_fit_camera()
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			camera_distance *= 0.9
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			camera_distance *= 1.1
	elif event is InputEventMouseMotion and dragging:
		camera_yaw -= event.relative.x * 0.01
		camera_pitch = clamp(camera_pitch - event.relative.y * 0.01, -1.4, 1.4)


func _process(_delta: float) -> void:
	if camera == null:
		return
	var offset := Vector3(
		camera_distance * cos(camera_pitch) * sin(camera_yaw),
		camera_distance * sin(camera_pitch),
		camera_distance * cos(camera_pitch) * cos(camera_yaw))
	camera.global_position = camera_target + offset
	camera.look_at(camera_target, Vector3.UP)


func _build_world() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.1, 0.14, 0.22)
	sky_material.sky_horizon_color = Color(0.35, 0.4, 0.48)
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.7
	environment.glow_enabled = true
	environment.glow_intensity = 0.5
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -32, 0)
	sun.light_energy = 1.4
	add_child(sun)

	var floor_instance := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(20, 20)
	floor_instance.mesh = plane
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color(0.13, 0.14, 0.17)
	floor_instance.material_override = floor_material
	add_child(floor_instance)

	camera = Camera3D.new()
	add_child(camera)
	camera.current = true


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_top = -96.0
	layer.add_child(panel)

	var box := VBoxContainer.new()
	panel.add_child(box)

	status_label = Label.new()
	box.add_child(status_label)

	var row := HBoxContainer.new()
	box.add_child(row)

	var open_button := Button.new()
	open_button.text = "Open .glb (O)"
	open_button.pressed.connect(func(): file_dialog.popup_centered())
	row.add_child(open_button)

	var prev_button := Button.new()
	prev_button.text = "< (Left)"
	prev_button.pressed.connect(next_animation.bind(-1))
	row.add_child(prev_button)

	anim_label = Label.new()
	row.add_child(anim_label)

	var next_button := Button.new()
	next_button.text = "> (Right)"
	next_button.pressed.connect(next_animation.bind(1))
	row.add_child(next_button)

	var pause_button := Button.new()
	pause_button.text = "Pause (Space)"
	pause_button.pressed.connect(_toggle_pause)
	row.add_child(pause_button)

	file_dialog = FileDialog.new()
	file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	file_dialog.filters = PackedStringArray(["*.glb ; glTF Binary", "*.gltf ; glTF"])
	file_dialog.file_selected.connect(load_model)
	layer.add_child(file_dialog)
