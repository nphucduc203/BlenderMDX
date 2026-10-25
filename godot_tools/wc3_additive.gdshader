shader_type spatial;
render_mode blend_add, depth_draw_opaque, cull_disabled, unshaded;

// WarCraft 3 Additive Blending Shader for Godot 4
// Adds color directly to the framebuffer without darkening backgrounds.

uniform sampler2D texture_albedo : source_color, filter_linear_mipmap, repeat_enable;
uniform vec4 tint_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float boost : hint_range(0.1, 5.0) = 1.0;

void fragment() {
	vec4 tex = texture(texture_albedo, UV);
	vec4 final_color = tex * tint_color;
	ALBEDO = vec3(0.0);
	EMISSION = final_color.rgb * final_color.a * boost;
}
