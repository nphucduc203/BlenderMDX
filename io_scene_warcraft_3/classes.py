import bpy


class WarCraft3Model:
    def __init__(self):
        self.name = None
        self.meshes = []
        self.materials = []
        self.textures = []
        self.nodes = []
        self.sequences = []
        self.geoset_animations = []
        self.pivot_points = []
        self.global_sequences = []
        self.texture_animations = []
        self.particle_emitters = []
        self.particle_emitters_2 = []
        self.ribbon_emitters = []

    def normalize_meshes_names(self):
        for mesh in self.meshes:
            mesh.name = self.name

class WarCraft3Bone:
    def __init__(self):
        self.type = 'bone'
        self.node = None
        self.geoset_id = None


class WarCraft3Helper:
    def __init__(self):
        self.type = 'helper'
        self.node = None


class WarCraft3Attachment:
    def __init__(self):
        self.type = 'attachment'
        self.node = None


class WarCraft3Event:
    def __init__(self):
        self.type = 'event'
        self.node = None


class WarCraft3CollisionShape:
    def __init__(self):
        self.type = 'collision_shape'
        self.node = None


class WarCraft3ParticleEmitter:
    def __init__(self):
        self.type = 'emitter'
        self.node = None
        self.emission_rate = 0.0
        self.gravity = 0.0
        self.longitude = 0.0
        self.latitude = 0.0
        self.path = ''
        self.life_span = 0.0
        self.speed = 0.0


class WarCraft3ParticleEmitter2:
    def __init__(self):
        self.type = 'emitter'
        self.node = None
        self.speed = 0.0
        self.variation = 0.0
        self.latitude = 0.0
        self.gravity = 0.0
        self.life_span = 0.0
        self.emission_rate = 0.0
        self.width = 0.0
        self.length = 0.0
        self.filter_mode = 0
        self.rows = 0
        self.columns = 0
        self.head_or_tail = 0
        self.tail_length = 0.0
        self.time_middle = 0.0
        self.segment_colors = [(1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)]
        self.segment_alphas = (255, 255, 255)
        self.segment_scaling = (1.0, 1.0, 1.0)
        self.texture_id = -1
        self.squirt = 0
        self.priority_plane = 0
        self.replaceable_id = 0


class WarCraft3RibbonEmitter:
    def __init__(self):
        self.type = 'ribbon'
        self.node = None
        self.height_above = 0.0
        self.height_below = 0.0
        self.alpha = 1.0
        self.color = (1.0, 1.0, 1.0)
        self.life_span = 0.0
        self.texture_slot = 0
        self.emission_rate = 0
        self.rows = 0
        self.columns = 0
        self.material_id = 0
        self.gravity = 0.0


class WarCraft3TextureAnimation:
    def __init__(self):
        self.translations = None
        self.rotations = None
        self.scalings = None


class WarCraft3Node:
    def __init__(self):
        self.name = None
        self.id = None
        self.parent = None
        self.translations = None
        self.rotations = None
        self.scalings = None


class WarCraft3GeosetTransformation:
    def __init__(self):
        self.tracks_count = None
        self.interpolation_type = None
        self.global_sequence_id = None
        self.times = []
        self.values = []


class WarCraft3Mesh:
    def __init__(self):
        self.name = None
        self.vertices = []
        self.normals = []
        self.triangles = []
        self.uvs = []
        self.material_id = None
        self.vertex_groups = []
        self.vertex_groups_ids = None


class WarCraft3Layer:
    def __init__(self):
        self.texture_id = 0
        self.filter_mode = 0
        self.shading_flags = 0
        self.coord_id = 0
        self.alpha = 1.0
        self.texture_animation_id = None
        self.material_alpha = None
        self.material_texture_id = None


class WarCraft3Material:
    def __init__(self):
        self.layers = []


class WarCraft3Texture:
    def __init__(self):
        self.image_file_name = None
        self.replaceable_id = None


class WarCraft3Sequence:
    def __init__(self):
        self.name = None
        self.interval_start = None
        self.interval_end = None


class WarCraft3GeosetAnimation:
    def __init__(self):
        self.geoset_id = None
        self.alpha = 1.0
        self.flags = 0
        self.color = (1.0, 1.0, 1.0)
        self.animation_color = None
        self.animation_alpha = None


class MDXImportProperties:
    def __init__(self):
        self.mdx_file_path = ''
        self.texture_search_dir = ''
        self.auto_import_textures = True
        self.team_color = None
        self.bone_size = 1.0
        self.use_custom_fps = False
        self.fps = 30
        self.frame_time = 1.0
        self.global_scale = 0.03
        self.import_particles = True

    def calculate_frame_time(self):
        if not self.use_custom_fps:
            self.fps = bpy.context.scene.render.fps
        
        # Ensure self.fps is a float or int, not a Blender property
        try:
            fps_val = float(self.fps)
        except TypeError:
            fps_val = 30.0 # Default fallback
            
        if fps_val <= 0:
            fps_val = 30.0
            
        self.frame_time = 1000.0 / fps_val
