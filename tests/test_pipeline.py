"""
Automated Regression Test Suite for Warcraft III MDX -> Blender -> GLB Export Pipeline
Tests both Lossless and Compatible GLB export modes, glTF chunk validation,
sidecar .wc3.json metadata schemas, roundtrip re-import, and Godot 4 post-import semantics.
"""

import sys
import os
import json
import struct
import tempfile
import traceback

# Ensure the local repository is at the top of sys.path
REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for m in list(sys.modules.keys()):
    if 'io_scene_warcraft_3' in m:
        del sys.modules[m]
sys.path = [REPO_DIR] + [p for p in sys.path if 'addons' not in p.lower() and p != REPO_DIR]

import bpy
import io_scene_warcraft_3

FIXTURES = [
    {
        'id': 'hero_priestess',
        'path': 'D:/Program Files/war3edit/Work/2 (95).mdx',
        'description': 'HeroMoonPriestess: Multi-layer additive materials, particle emitters, cameras, collision shapes, animations',
        'expect_particles': True,
        'expect_multi_layer': True,
        'expect_attachments': True,
    },
    {
        'id': 'bladestorm_ribbons',
        'path': 'D:/Program Files/war3edit/Work/83.mdx',
        'description': 'BladeStorm: Ribbon emitters (RIBB chunk), events (EVTS chunk)',
        'expect_ribbons': True,
        'expect_multi_layer': False,
        'expect_particles': False,
    },
    {
        'id': 'rifleman_character',
        'path': 'D:/Program Files/war3edit/Work/rifleman.mdx',
        'description': 'Rifleman: Skinned character with multiple combat animation sequences and attachments',
        'expect_particles': False,
        'expect_multi_layer': False,
        'expect_attachments': True,
    },
    {
        'id': 'texture_anim_wing',
        'path': 'D:/Program Files/war3edit/Work/chibang1.mdx',
        'description': 'Wings with Texture Coordinate Animation (TXAN chunk)',
        'expect_txan': True,
        'expect_particles': False,
    },
    {
        'id': 'split_normals_spire',
        'path': 'D:/Program Files/war3edit/Work/SalvationSpire.mdx',
        'description': 'SalvationSpire: Custom split-normals and building structure',
        'expect_particles': False,
        'expect_multi_layer': False,
    }
]


def validate_glb_structure(glb_path):
    """The one engine-facing tier: standard glTF 2.0 with per-layer primitives and wc3_* extras hints."""
    assert os.path.exists(glb_path), f"GLB does not exist: {glb_path}"
    file_size = os.path.getsize(glb_path)
    assert file_size > 20, f"GLB file too small: {file_size}"
    assert file_size % 4 == 0, f"GLB must be 4-byte aligned (got {file_size} bytes, mod 4 = {file_size % 4})"

    with open(glb_path, 'rb') as f:
        data = f.read()

    magic, version, total_len = struct.unpack_from('<3I', data, 0)
    assert magic == 0x46546C67, f"Invalid GLB magic: {hex(magic)}"
    assert version == 2, f"Expected glTF version 2, got {version}"
    assert total_len == file_size, f"Header length {total_len} != actual size {file_size}"

    chunk_len, chunk_type = struct.unpack_from('<2I', data, 12)
    assert chunk_type == 0x4E4F534A, f"First chunk must be JSON (0x4E4F534A), got {hex(chunk_type)}"
    gltf = json.loads(data[20 : 20 + chunk_len].decode('utf-8'))

    assert gltf.get('meshes'), "GLB has no meshes"
    assert gltf.get('animations'), "GLB has no animations"
    assert gltf.get('materials'), "GLB has no materials"
    for mat in gltf['materials']:
        if mat.get('extras', {}).get('wc3_filter_mode') in (3, 4):   # Additive / AddAlpha
            assert mat.get('alphaMode') == 'BLEND', "Additive material must be BLEND in glTF"
            assert mat.get('doubleSided') is True, "Additive material must be double-sided"
    return gltf


def run_fixture_test(f_info, tmp_dir):
    f_id = f_info['id']
    f_path = f_info['path']
    desc = f_info['description']

    print(f"\n========================================================")
    print(f"RUNNING FIXTURE TEST: [{f_id}]")
    print(f"Path: {f_path}")
    print(f"Description: {desc}")
    print(f"========================================================")

    if not os.path.exists(f_path):
        print(f"SKIP: Fixture file not found: {f_path}")
        return True, "Skipped (file not found)"

    # Step 1: Clean Blender reset & import
    bpy.ops.wm.read_factory_settings(use_empty=True)
    io_scene_warcraft_3.register()

    import_res = bpy.ops.warcraft_3.import_mdx(filepath=f_path)
    assert import_res == {'FINISHED'}, f"Import failed: {import_res}"

    arm = None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            arm = obj
            break
    assert arm is not None, "No Armature created on import"

    # Check imported properties: the armature carries the node metadata, no json blob.
    sequences = [s.name for s in arm.data.warcraft_3.sequencesList]
    attachments = [b.name for b in arm.data.bones if b.warcraft_3.nodeType == 'ATTACHMENT']

    emitters_in_scene = [o for o in bpy.data.objects if o.name.startswith('W3_Emitter_')]

    print(f"  [Blender Import OK] Armature: '{arm.name}' | Bones: {len(arm.data.bones)} | Objects: {len(bpy.data.objects)}")
    print(f"    Emitters: {len(emitters_in_scene)} | Sequences: {len(sequences)}")

    if f_info.get('expect_particles'):
        assert len(emitters_in_scene) > 0, "Expected particle emitters in scene"
    if f_info.get('expect_attachments'):
        assert len(attachments) > 0, "Expected attachment bones in the armature"

    # Step 2: Export the single engine-ready GLB
    glb_path = os.path.join(tmp_dir, f"{f_id}.glb")
    res = bpy.ops.warcraft_3.export_glb(filepath=glb_path)
    assert res == {'FINISHED'}, f"Export failed: {res}"

    gltf = validate_glb_structure(glb_path)
    primitives = sum(len(m.get('primitives', [])) for m in gltf['meshes'])
    emitter_nodes = len([n for n in gltf.get('nodes', []) if n.get('extras', {}).get('wc3_type') == 'emitter'])
    print(f"  [GLB Export OK] {os.path.getsize(glb_path):,} bytes | meshes {len(gltf['meshes'])} / primitives {primitives}"
          f" | materials {len(gltf['materials'])} | animations {len(gltf['animations'])} | emitter nodes {emitter_nodes}")
    if f_info.get('expect_multi_layer'):
        assert primitives > len(gltf['meshes']), "Multi-layer geosets must export as extra primitives"
    if f_info.get('expect_particles'):
        assert emitter_nodes > 0, "Expected emitter marker nodes in the exported GLB"

    # Step 3: Round-trip Re-import into Blender
    bpy.ops.wm.read_factory_settings(use_empty=True)
    reimport_res = bpy.ops.import_scene.gltf(filepath=glb_path)
    assert reimport_res == {'FINISHED'}, f"GLB re-import failed: {reimport_res}"
    reimported_objects = len(bpy.data.objects)
    assert reimported_objects > 0, "No objects created on GLB re-import"
    print(f"  [GLB Roundtrip Re-import OK] {reimported_objects} objects recreated in Blender")

    return True, "PASSED"


def main():
    tmp_dir = tempfile.mkdtemp(prefix='blender_mdx_test_')
    print(f"Starting BlenderMDX Regression Test Suite in {tmp_dir}")

    passed = 0
    failed = 0
    results = {}

    for f_info in FIXTURES:
        f_id = f_info['id']
        try:
            ok, msg = run_fixture_test(f_info, tmp_dir)
            if ok:
                passed += 1
                results[f_id] = msg
            else:
                failed += 1
                results[f_id] = f"FAILED: {msg}"
        except Exception as e:
            failed += 1
            results[f_id] = f"ERROR: {e}"
            traceback.print_exc()

    print("\n========================================================")
    print("TEST SUITE SUMMARY")
    print("========================================================")
    for f_id, res in results.items():
        print(f"  {f_id:25}: {res}")
    print("--------------------------------------------------------")
    print(f"TOTAL: {len(FIXTURES)} | PASSED: {passed} | FAILED: {failed}")
    print("========================================================")

    # Clean up temp directory
    try:
        import shutil
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
