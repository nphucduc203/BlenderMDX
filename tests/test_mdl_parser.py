"""Plain-Python test for the .mdl text parser (no Blender needed).

Run:  python tests/test_mdl_parser.py
"""

import os
import sys
import types
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Import mdl without running the addon's __init__, which pulls in the whole Blender API.
# bpy is still stubbed because classes.py imports it at module scope.
for name in ('bpy', 'bpy.props', 'bpy.types', 'bpy.utils', 'bpy_extras', 'mathutils'):
    sys.modules.setdefault(name, MagicMock())
package = types.ModuleType('io_scene_warcraft_3')
package.__path__ = [os.path.join(ROOT, 'io_scene_warcraft_3')]
sys.modules['io_scene_warcraft_3'] = package

from io_scene_warcraft_3 import mdl  # noqa: E402

SAMPLE = '''
Version { FormatVersion 800 }
Model "TestModel" {
    NumGeosets 1,
    NumBones 2,
    BlendTime 150,
}
Sequences 2 {
    Anim "Stand" {
        Interval { 0, 31 },
        NonLooping,
    }
    Anim "Death" {
        Interval { 32, 63 },
    }
}
GlobalSequences 1 {
    Duration 5000,
}
Textures 2 {
    Bitmap { Image "ReplaceableTextures\\\\TeamColor\\\\TeamColor.blp", ReplaceableId 1 },
    Bitmap { Image "Units\\\\Human\\\\Footman\\\\Footman.blp", WrapWidth, WrapHeight },
}
Materials 1 {
    Material {
        Layer {
            FilterMode "Blend",
            Alpha 0.500000,
            TextureID 1,
            CoordId 0,
            Unshaded,
            TwoSided,
        }
        Layer {
            FilterMode "Additive",
            static Alpha 0.250000,
            TextureID 0,
            TVertexAnimId 0,
        }
        Layer {
            FilterMode "Blend",
            Alpha 3 {
                0: 1.0,
                500: 0.5,
                1000: 0.0,
            },
            TextureID 2 {
                Linear,
                0: 0,
                500: 1,
            },
            TextureAnimID 0,
        }
    }
}
TextureAnims 1 {
    TVertexAnim {
        Translation { 2 { Linear, 0: { 0.0, 0.0, 0.0 }, 1000: { 1.0, 0.0, 0.0 }, }, },
    }
}
Geoset {
    Vertices 3 {
        { 1.0, 2.0, 3.0 },
        { 4.0, 5.0, 6.0 },
        { 7.0, 8.0, 9.0 },
    }
    Normals 3 {
        { 0.0, 0.0, 1.0 },
        { 0.0, 0.0, 1.0 },
        { 0.0, 0.0, 1.0 },
    }
    TVertices 3 {
        { 0.0, 0.0 },
        { 1.0, 0.0 },
        { 0.5, 1.0 },
    }
    VertexGroup { 0, 0, 1 }
    Faces 1 3 {
        Triangles {
            { 0, 1, 2 },
        }
    }
    Groups 2 2 {
        Matrices { 0 },
        Matrices { 1 },
    }
    MinimumExtent { -1.0, -1.0, -1.0 },
    MaximumExtent { 1.0, 1.0, 1.0 },
    BoundsRadius 10.0,
    LevelOfDetail 0,
    Name "layer0",
    Anim {
        Alpha { 2 { Linear, 0: 1.0, 500: 0.0 }, },
        Color { 2 { Linear, 0: { 0.0, 0.5, 1.0 }, 500: { 0.0, 0.5, 1.0 }, }, },
    }
    MaterialID 0,
    SelectionGroup 0,
    Unselectable,
}
GeosetAnim {
    GeosetId 0,
    static Alpha 0.750000,
    static Color { 0.0, 0.5, 1.0 },
    DropShadow,
}
Bone "Bip01" {
    ObjectId 0,
    Parent -1,
    GeosetId Multiple,
    GeosetAnimId None,
    Translation { 2 { Linear, 0: { 0.0, 0.0, 0.0 }, 1000: { 10.0, 0.0, 0.0 }, }, },
    Rotation { 2 { Linear, 0: { 0.0, 0.0, 0.0, 1.0 }, 1000: { 0.0, 0.7071, 0.0, 0.7071 }, }, },
}
Bone "Bip02" {
    ObjectId 1,
    Parent 0,
    GeosetId 0,
    GeosetAnimId 0,
    Billboarded,
    DontInherit { Scaling },
}
Helper "Attachment" {
    ObjectId 2,
    Parent 1,
}
Attachment "Weapon" {
    ObjectId 3,
    Parent 2,
    Path "Abilities\\Spells\\Human\\Blizzard\\BlizzardTarget.mdl",
    AttachmentID 0,
}
ParticleEmitter2 "Smoke" {
    ObjectId 4,
    Parent 0,
    Speed 40.0,
    Variation 0.200,
    Latitude 360.0,
    Gravity 25.0,
    EmissionRate 13.0,
    LifeSpan 1.0,
    Width 8.0,
    Length 0.100,
    Additive,
    Both,
    TailLength 8.0,
    Time 0.660,
    Rows 2,
    Columns 4,
    Alpha { 255, 255, 255 },
    ParticleScaling { 0.800, 1.0, 1.200 },
    SegmentColor {
        Color { 0.2, 0.5, 1.0 },
        Color { 0.3, 0.4, 0.5 },
        Color { 0.1, 0.1, 0.1 },
    }
    LifeSpanUVAnim { 0, 7 },
    DecayUVAnim { 8, 15 },
    TextureID 1,
    ReplaceableId 0,
    Visibility { 2 { Linear, 0: 1.0, 1000: 0.0, }, },
}
RibbonEmitter "Ribbon" {
    ObjectId 5,
    Parent 0,
    MaterialID 0,
    Color { 1.0, 1.0, 1.0 },
    Alpha 1.0,
    HeightAbove 30.0,
    HeightBelow 30.0,
    EmissionRate 2,
    Rows 2,
    Columns 4,
    LifeSpan 0.5,
    Gravity 0.0,
    TextureSlot 0,
}
CollisionShape "Hd" {
    ObjectId 6,
    Parent 0,
    Box,
    Vertices 8 {
        { 1.0, 1.0, 1.0 },
        { 1.0, 1.0, -1.0 },
    }
}
EventObject "Splash" {
    ObjectId 7,
    Parent 0,
    EventTrack 2 { 32, 48 }
}
Light "L" {
    ObjectId 8,
    Parent 0,
    Ambient,
    Color { 2 { Linear, 0: { 0.0, 0.5, 1.0 }, 500: { 0.0, 0.5, 1.0 }, }, },
    static Intensity 1.0,
    AttenuationStart 100.0,
    AttenuationEnd 300.0,
}
Camera "Cam" {
    Position { 0.0, 0.0, 0.0 },
    FieldOfView 0.7854,
    NearClip 0.1,
    FarClip 16384.0,
    Target { Position { 0.0, 1.0, 0.0 } },
}
PivotPoints 3 {
    { 0.0, 0.0, 0.0 },
    { 10.0, 0.0, 0.0 },
    { 0.0, 50.0, 0.0 },
}
/* Block comments are not in the reference grammar, but real editors emit them. */
Sound "footman" {
    Type "footman,Attack",
}
'''


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_sample():
    model = mdl.parse_mdl(SAMPLE)
    check(model.version == 800, 'version')
    check(model.name == 'TestModel', 'name')
    check(len(model.sequences) == 2 and model.sequences[0].interval_end == 31, 'sequences')
    check(model.sequences[0].flags == 1 and model.sequences[1].flags == 0, 'NonLooping flag')
    check(model.global_sequences == [5000], 'global sequences')

    check(len(model.textures) == 2, 'texture count: {0}'.format(len(model.textures)))
    check(model.textures[0].replaceable_id == 1, 'replaceable id')
    check(model.textures[1].flags == 3, 'wrap flags')

    check(len(model.materials) == 1, 'material count')
    layers = model.materials[0].layers
    check(len(layers) == 3, 'layer count: {0}'.format(len(layers)))
    check(layers[0].filter_mode == 2 and layers[0].texture_id == 1, 'layer0')
    check(abs(layers[0].alpha - 0.5) < 1e-6, 'layer0 alpha')
    check(layers[0].shading_flags == 0x1 | 0x10, 'layer0 shading flags')
    check(layers[1].filter_mode == 3 and abs(layers[1].alpha - 0.25) < 1e-6, 'layer1')
    check(layers[1].texture_animation_id == 0, 'layer1 texture anim id')
    # Layer 2 carries the MDX-equivalent KMTA / KMTF tracks and the 'TextureAnimID' alias.
    kmta = layers[2].material_alpha
    check(kmta and kmta.tracks_count == 3 and list(kmta.values) == [1.0, 0.5, 0.0],
          'layer2 alpha track: {0}'.format(kmta))
    check(abs(layers[2].alpha - 1.0) < 1e-6, 'layer2 static alpha falls back to the first key')
    kmtf = layers[2].material_texture_id
    check(kmtf and list(kmtf.values) == [0, 1], 'layer2 flipbook track: {0}'.format(kmtf))
    check(layers[2].texture_id == 0, 'layer2 texture id from the first flipbook key')
    check(layers[2].texture_animation_id == 0, 'layer2 TextureAnimID alias')

    mesh = model.meshes[0]
    check(len(mesh.vertices) == 3 and mesh.vertices[2] == (7.0, 8.0, 9.0), 'vertices')
    check(mesh.triangles == [(0, 1, 2)], 'triangles: {0}'.format(mesh.triangles))
    check(mesh.uvs[1] == (1.0, 1.0), 'uv v is flipped: {0}'.format(mesh.uvs[1]))
    check(mesh.vertex_groups == [[0], [0], [1]], 'vertex groups: {0}'.format(mesh.vertex_groups))
    check(mesh.vertex_groups_ids == [0, 1], 'vertex group ids')
    check(mesh.material_id == 0 and mesh.selection_flags == 1, 'geoset material/selection')

    anim = model.geoset_animations[0]
    check(anim.geoset_id == 0 and abs(anim.alpha - 0.75) < 1e-6, 'geoset anim')
    check(anim.color == (1.0, 0.5, 0.0), 'geoset anim color: {0}'.format(anim.color))
    check(anim.flags == 1 | 2, 'geoset anim flags')
    check(anim.animation_color.tracks_count == 1 and anim.animation_color.times == [0], 'synthesized color track')

    check(len(model.texture_animations) == 1, 'texture anims')
    translation = model.texture_animations[0].translations
    check(translation.tracks_count == 2 and translation.values[1] == (1.0, 0.0, 0.0), 'texture anim track')

    bones = [n for n in model.nodes if getattr(n, 'type', None) == 'bone']
    check(len(bones) == 2, 'bone count: {0}'.format(len(bones)))
    check(bones[0].node.name == 'Bip01' and bones[0].node.parent is None, 'bone0 node')
    check(bones[0].geoset_id is None, 'GeosetId Multiple')
    check(bones[1].geoset_id == 0 and bones[1].geoset_animation_id == 0, 'bone1 ids')
    check(bones[1].node.flags == 0x8 | 0x4, 'bone1 flags: {0}'.format(bones[1].node.flags))
    # MDL writes xyzw, the addon keeps wxyz
    check(bones[0].node.rotations.values[1] == (0.7071, 0.0, 0.7071, 0.0),
          'quat order: {0}'.format(bones[0].node.rotations.values[1]))
    check(bones[0].node.translations.global_sequence_id is None, 'global seq id')

    emitter = model.particle_emitters_2[0]
    check(abs(emitter.speed - 40.0) < 1e-6 and abs(emitter.latitude - 360.0) < 1e-6, 'emitter scalars')
    check(emitter.filter_mode == 1, 'emitter filter mode from bare keyword: {0}'.format(emitter.filter_mode))
    check(emitter.head_or_tail == 2, 'emitter Head/Tail/Both')
    check(emitter.segment_alphas == (255, 255, 255), 'emitter alphas')
    check(emitter.segment_colors[1] == (0.5, 0.4, 0.3), 'emitter segment color')
    check(emitter.segment_colors[0] == (1.0, 0.5, 0.2), 'emitter segment color is BGR: {0}'.format(
        emitter.segment_colors[0]))
    check(emitter.texture_id == 1 and emitter.columns == 4, 'emitter texture/rows')
    check(emitter.visibility_track.values == [1.0, 0.0], 'emitter visibility track')

    ribbon = model.ribbon_emitters[0]
    check(abs(ribbon.height_above - 30.0) < 1e-6 and ribbon.rows == 2, 'ribbon')
    check(ribbon.color == (1.0, 1.0, 1.0), 'ribbon color')

    check(model.cameras[0].target_position == (0.0, 1.0, 0.0), 'camera target')
    check(abs(model.cameras[0].field_of_view - 0.7854) < 1e-6, 'camera fov')
    check(model.lights[0].light_type == 2 and abs(model.lights[0].intensity - 1.0) < 1e-6, 'light')
    check(model.lights[0].color == (1.0, 0.5, 0.0),
          'light color is BGR: {0}'.format(model.lights[0].color))
    check(model.lights[0].color_track.values[0] == (1.0, 0.5, 0.0),
          'light color track is BGR: {0}'.format(model.lights[0].color_track.values[0]))
    # Both formats land in model.nodes; there are no per-type lists (parity with parser.py).
    def nodes_of(kind):
        return [n for n in model.nodes if getattr(n, 'type', None) == kind]

    check(nodes_of('collision_shape')[0].shape_type == 0, 'collision shape type')
    check(nodes_of('event')[0].tracks == [32, 48], 'event track: {0}'.format(nodes_of('event')[0].tracks))
    check(len(nodes_of('attachment')) == 1, 'attachment count')
    check(nodes_of('attachment')[0].attachment_id == 0, 'attachment id')
    check(model.pivot_points == [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 50.0, 0.0)], 'pivot points')
    check(len(model.nodes) == 9, 'node count: {0}'.format(len(model.nodes)))
    print('ok  synthetic mdl  ->  {0} meshes, {1} nodes, {2} emitters'.format(
        len(model.meshes), len(model.nodes), len(model.particle_emitters_2)))


def test_truncated_file_does_not_crash():
    """Work/123.mdl is a truncated export (unclosed Geoset, no faces): it must degrade, not throw."""
    path = r'D:\Program Files\war3edit\Work\123.mdl'
    if not os.path.exists(path):
        print('skip  123.mdl not present')
        return
    with open(path, 'rb') as handle:
        model = mdl.parse_mdl(handle.read())
    check(model.name == '', 'no Model block means an empty name')
    check(len(model.meshes) == 1 and len(model.meshes[0].vertices) == 2415,
          'truncated geoset still yields its vertices: {0}'.format(len(model.meshes[0].vertices)))
    print('ok  truncated mdl  ->  {0} vertices recovered'.format(len(model.meshes[0].vertices)))


if __name__ == '__main__':
    test_sample()
    test_truncated_file_does_not_crash()
    print('PASS')
