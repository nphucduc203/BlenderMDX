"""Plain-Python regression test for the Reforged binary layouts (no Blender needed).

Builds a minimal v900/v1000 MDX by hand: 336-byte MODL name, MTLS shader + layer
emissive/fresnel fields, GEOS LOD/name + TANG/SKIN chunks, both collision shape
layouts, and raw RGB geoset colors.

Run:  python tests/test_mdx_reforged.py
"""

import os
import struct
import sys
import types
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for name in ('bpy', 'bpy.props', 'bpy.types', 'bpy.utils', 'bpy_extras', 'mathutils',
             'bpy.ops', 'bpy.path', 'bpy.app', 'bpy.context'):
    sys.modules.setdefault(name, MagicMock())
package = types.ModuleType('io_scene_warcraft_3')
package.__path__ = [os.path.join(ROOT, 'io_scene_warcraft_3')]
sys.modules['io_scene_warcraft_3'] = package

from io_scene_warcraft_3 import parser  # noqa: E402

parser.importer.load_warcraft_3_model = lambda model, props: model


def chunk(chunk_id, body):
    return chunk_id.encode('latin1') + struct.pack('<I', len(body)) + body


def sub(chunk_id, payload):
    return chunk_id.encode('latin1') + struct.pack('<I', len(payload)) + payload


def gpart(chunk_id, count, data):
    """GEOS sub-chunks are a tag plus an element count, with no size field."""
    return chunk_id.encode('latin1') + struct.pack('<I', count) + data


def build_geoset(version):
    body = gpart('VRTX', 3, struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0))
    body += gpart('NRMS', 3, struct.pack('<9f', 0, 0, 1, 0, 0, 1, 0, 0, 1))
    body += gpart('PTYP', 1, struct.pack('<I', 4))
    body += gpart('PCNT', 1, struct.pack('<I', 3))
    body += gpart('PVTX', 3, struct.pack('<3H', 0, 1, 2))
    body += gpart('GNDX', 3, bytes((0, 0, 1)))
    body += gpart('MTGC', 2, struct.pack('<2I', 1, 1))
    body += gpart('MATS', 2, struct.pack('<2I', 0, 1))
    body += struct.pack('<3I', 0, 0, 0)    # material, selection group, unselectable
    if version >= 900:
        body += struct.pack('<I', 0) + b'geoset-name'.ljust(80, b'\x00')
    body += struct.pack('<7f', 10.0, -1, -1, -1, 1, 1, 1)    # extent
    body += struct.pack('<I', 0)    # extent count
    if version >= 900:
        body += gpart('TANG', 3, struct.pack('<12f', *([1.0] * 12)))    # TANG/SKIN use a byte count
        body += gpart('SKIN', 3, bytes((0, 1, 2)))
    body += gpart('UVAS', 1, gpart('UVBS', 3, struct.pack('<6f', 0, 0, 1, 0, 0.5, 1)))
    return struct.pack('<I', 4 + len(body)) + body


def build_material(version):
    layer = struct.pack('<5If', 2, 0, 0, 0xffffffff, 0, 0.25)
    if version >= 900:
        layer += struct.pack('<f', 1.0)    # emissive gain
        if version >= 1000:
            layer += struct.pack('<3f', 1.0, 1.0, 1.0)
            layer += struct.pack('<2f', 1.0, 1.0)    # fresnel opacity, team color
    layer += b'KMTA' + struct.pack('<III', 1, 1, 0xffffffff) + struct.pack('<If', 0, 0.5)
    layer = struct.pack('<I', 4 + len(layer)) + layer
    lays = b'LAYS' + struct.pack('<I', 1) + layer
    shader = b'shader'.ljust(80, b'\x00') if 900 <= version < 1100 else b''
    body = struct.pack('<iI', 0, 4) + shader + lays
    return struct.pack('<I', 4 + len(body)) + body


def build_collision(node_name, shape, vertices, radius=None):
    node_body = node_name.encode().ljust(80, b'\x00') + struct.pack('<3I', 0, 0xffffffff, 0)
    node = struct.pack('<I', 4 + len(node_body)) + node_body
    body = node + struct.pack('<I', shape)
    body += b''.join(struct.pack('<3f', *v) for v in vertices)
    if radius is not None:
        body += struct.pack('<f', radius)
    return body


def build_mdx(version):
    model_body = b'ReforgedModel'.ljust(336, b'\x00') + struct.pack('<I', 0)
    model_body += struct.pack('<7f', 1, 0, 0, 0, 0, 0, 0) + struct.pack('<I', 150)

    geoa_body = struct.pack('<I', 28) + struct.pack('<f', 1.0) + struct.pack('<I', 0)
    geoa_body += struct.pack('<3f', 0.1, 0.2, 0.3) + struct.pack('<I', 0)

    collision = build_collision('Cylinder', 1, [(1.0, 2.0, 3.0)])
    collision += build_collision('Box', 0, [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)])

    data = b'MDLX'
    data += chunk('VERS', struct.pack('<I', version))
    data += chunk('MODL', model_body)
    data += chunk('GEOS', build_geoset(version))
    data += chunk('MTLS', build_material(version))
    data += chunk('GEOA', geoa_body)
    data += chunk('CLID', collision)
    return data


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_version(version):
    model = parser.parse_mdx(build_mdx(version), None)
    check(model.version == version, 'version')
    check(model.name == 'ReforgedModel', '336-byte model name: {0!r}'.format(model.name))

    mesh = model.meshes[0]
    check(mesh.triangles == [(0, 1, 2)], 'triangles: {0}'.format(mesh.triangles))
    check(mesh.vertices[1] == (1.0, 0.0, 0.0), 'vertices')
    check(mesh.uv_sets == [[(0.0, 1.0), (1.0, 1.0), (0.5, 0.0)]], 'uvs: {0}'.format(mesh.uv_sets))
    check(mesh.vertex_groups == [[0], [0], [1]], 'vertex groups: {0}'.format(mesh.vertex_groups))
    check(mesh.vertex_groups_ids == [0, 1], 'vertex group ids')
    check(mesh.material_id == 0, 'material id')

    layer = model.materials[0].layers[0]
    check(layer.filter_mode == 2 and abs(layer.alpha - 0.25) < 1e-6, 'layer header')
    check(layer.material_alpha.tracks_count == 1 and layer.material_alpha.values == [0.5],
          'layer alpha track')

    color = model.geoset_animations[0].color
    check(all(abs(a - b) < 1e-6 for a, b in zip(color, (0.1, 0.2, 0.3))),
          'geoset color is stored as RGB: {0}'.format(color))

    shapes = model.collision_shapes
    check(len(shapes) == 2, 'collision shapes: {0}'.format(len(shapes)))
    check(shapes[0].shape_type == 1 and shapes[0].vertices == [(1.0, 2.0, 3.0)],
          'cylinder layout: {0}'.format(shapes[0].vertices))
    check(shapes[1].shape_type == 0
          and shapes[1].vertices == [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
          'box layout: {0}'.format(shapes[1].vertices))

    print('ok  synthetic mdx v{0}  ->  {1} material layer, {2} collision shapes'.format(
        version, len(model.materials[0].layers), len(shapes)))


if __name__ == '__main__':
    test_version(900)
    test_version(1000)
    print('PASS')
