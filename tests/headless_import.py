"""Headless smoke test: register the addon and import a model into an empty scene.

Run:  blender --background --python tests/headless_import.py -- "D:/path/to/model.mdx"
Add --export after the path to also run both GLB exporters and check the output.
Exits non-zero when the import raises, so it also works as a parser/material regression check.
"""

import json
import os
import struct
import sys
import tempfile
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import bpy

# An enabled installed copy shadows the repo package and makes this test meaningless.
if 'io_scene_warcraft_3' in bpy.context.preferences.addons:
    bpy.ops.preferences.addon_disable(module='io_scene_warcraft_3')
for module_name in [m for m in sys.modules if m == 'io_scene_warcraft_3' or m.startswith('io_scene_warcraft_3.')]:
    del sys.modules[module_name]
sys.path.insert(0, REPO)

import io_scene_warcraft_3
from io_scene_warcraft_3 import classes, parser

assert os.path.dirname(os.path.abspath(io_scene_warcraft_3.__file__)) == os.path.join(
    REPO, 'io_scene_warcraft_3'), 'loaded the installed addon, not the repo: ' + io_scene_warcraft_3.__file__

DEFAULT_MODEL = r'D:\Program Files\war3edit\Work\2 (95).mdx'


def import_model(path):
    properties = classes.MDXImportProperties()
    properties.mdx_file_path = path
    properties.texture_search_dir = os.path.dirname(path)
    properties.auto_import_textures = True
    properties.import_particles = True
    properties.set_team_color = 'RED'
    properties.bone_size = 5.0
    properties.global_scale = 0.03
    properties.calculate_frame_time()
    return parser.load_mdx(properties)


def report():
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    print('objects       :', len(meshes))
    print('materials     :', len(bpy.data.materials))
    print('images        :', len(bpy.data.images))
    print('armatures     :', len(bpy.data.armatures))
    print('actions       :', len(bpy.data.actions))
    print('particle mods :', sum(1 for o in meshes for m in o.modifiers if m.type == 'PARTICLE_SYSTEM'))
    layered = [m for m in bpy.data.materials if len(m.get('wc3_layers_data', [])) > 1]
    print('multi-layer   :', len(layered))
    graphed = [m for m in bpy.data.materials
               if m.use_nodes and any(n.type == 'MIX' for n in m.node_tree.nodes)]
    print('composited    :', len(graphed))


def glb_stats(path):
    """Read the GLB header + JSON chunk and report what the exporter actually produced."""
    with open(path, 'rb') as f:
        head = f.read(20)
        magic, version, length = struct.unpack('<4sII', head[:12])
        chunk_len, chunk_type = struct.unpack('<I4s', head[12:20])
        json_obj = json.loads(f.read(chunk_len))
    assert magic == b'glTF' and version == 2, f'{path}: bad header {magic!r} v{version}'
    prims = sum(len(mesh.get('primitives', [])) for mesh in json_obj.get('meshes', []))
    return {
        'bytes': length,
        'meshes': len(json_obj.get('meshes', [])),
        'primitives': prims,
        'materials': len(json_obj.get('materials', [])),
        'animations': len(json_obj.get('animations', [])),
        'nodes': len(json_obj.get('nodes', [])),
        'extensions': sorted(json_obj.get('extensionsUsed', [])),
    }


def export_models():
    """Run the engine exporter into a temp dir; a raise or a CANCELLED result fails the test."""
    path = os.path.join(tempfile.gettempdir(), 'wc3_smoke.glb')
    result = bpy.ops.warcraft_3.export_glb(filepath=path)
    assert result == {'FINISHED'}, f'export returned {result}'
    print('export      :', glb_stats(path))
    # The exporters must leave the scene exactly as they found it.
    leftovers = [m.name for m in bpy.data.materials if 'W3_Export' in m.name or m.name.endswith('.tmp')]
    assert not leftovers, f'export left temp materials: {leftovers}'
    return 0


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    path = next((a for a in argv if not a.startswith('--')), DEFAULT_MODEL)
    io_scene_warcraft_3.register()
    print('importing', path)
    try:
        import_model(path)
    except Exception:
        traceback.print_exc()
        return 1
    report()
    if '--export' in argv:
        return export_models()
    return 0


if __name__ == '__main__':
    sys.exit(main())
