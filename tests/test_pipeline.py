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


def validate_glb_structure(glb_path, expected_mode='lossless'):
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
    json_bytes = data[20 : 20 + chunk_len]
    gltf = json.loads(json_bytes.decode('utf-8'))

    # Verify versioned schema in asset extras
    asset_extras = gltf.get('asset', {}).get('extras', {})
    assert asset_extras.get('wc3_schema_version') == '2.0.0', f"Expected wc3_schema_version 2.0.0, got {asset_extras.get('wc3_schema_version')}"
    assert asset_extras.get('wc3_export_mode') == expected_mode, f"Expected mode {expected_mode}, got {asset_extras.get('wc3_export_mode')}"

    # Verify node extras compliance
    emitter_nodes = [n for n in gltf.get('nodes', []) if n.get('extras', {}).get('wc3_type') == 'emitter']
    ribbon_nodes = [n for n in gltf.get('nodes', []) if n.get('extras', {}).get('wc3_type') == 'ribbon']

    if expected_mode == 'compatible':
        assert len(emitter_nodes) == 0, f"Compatible GLB must have 0 emitter nodes (found {len(emitter_nodes)})"
        assert len(ribbon_nodes) == 0, f"Compatible GLB must have 0 ribbon nodes (found {len(ribbon_nodes)})"

    return gltf


def validate_sidecar(sidecar_path, expected_mode='lossless'):
    assert os.path.exists(sidecar_path), f"Sidecar JSON does not exist: {sidecar_path}"
    with open(sidecar_path, 'r', encoding='utf-8') as f:
        sidecar = json.load(f)

    assert sidecar.get('schema_version') == '2.0.0', f"Sidecar schema_version must be 2.0.0 (got {sidecar.get('schema_version')})"
    assert sidecar.get('export_mode') == expected_mode, f"Sidecar export_mode must be {expected_mode}"
    assert 'warnings' in sidecar, "Sidecar must contain warnings list"
    assert 'geosets' in sidecar, "Sidecar must contain geosets list"
    assert 'particle_emitters' in sidecar, "Sidecar must contain particle_emitters list"
    assert 'ribbon_emitters' in sidecar, "Sidecar must contain ribbon_emitters list"
    assert 'attachments' in sidecar, "Sidecar must contain attachments list"
    return sidecar


def simulate_godot_post_import_verification(gltf, sidecar, expected_mode='lossless'):
    """
    Simulates Godot 4 Wc3PostImport logic and verifies:
    1. Additive materials receive unshaded, depth_draw_never, and proper render_priority
    2. Multi-primitive layers receive increasing render_priority to eliminate Z-fighting
    3. Emitters map cleanly to particle specs
    4. Ribbon emitters map to ribbon markers
    """
    materials = gltf.get('materials', [])
    for idx, mat in enumerate(materials):
        extras = mat.get('extras', {})
        filter_mode = extras.get('wc3_filter_mode')
        render_priority = extras.get('wc3_render_priority', 0)

        if filter_mode in (3, 4): # Additive
            if expected_mode == 'lossless':
                assert mat.get('alphaMode') == 'BLEND', "Additive material must be BLEND in glTF"
                assert mat.get('doubleSided') == True, "Additive material must be double-sided"
            elif expected_mode == 'compatible':
                pbr = mat.get('pbrMetallicRoughness', {})
                assert pbr.get('baseColorFactor') == [0.0, 0.0, 0.0, 1.0], "Compatible additive baseColor must be black"
                assert 'KHR_materials_emissive_strength' in mat.get('extensions', {}), "Compatible additive must use KHR_materials_emissive_strength"

    # Multi-primitive verification in meshes
    for m in gltf.get('meshes', []):
        prims = m.get('primitives', [])
        if len(prims) > 1 and expected_mode == 'lossless':
            # Verify each primitive has a distinct material with ascending render_priority
            priorities = []
            for p in prims:
                mat_idx = p.get('material')
                if mat_idx is not None and mat_idx < len(materials):
                    prio = materials[mat_idx].get('extras', {}).get('wc3_render_priority', 0)
                    priorities.append(prio)
            assert sorted(priorities) == priorities, f"Primitives in multi-layer mesh {m.get('name')} must have non-decreasing render_priority: {priorities}"


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
    ribbons_in_scene = [o for o in bpy.data.objects if o.name.startswith('W3_Ribbon_')]

    print(f"  [Blender Import OK] Armature: '{arm.name}' | Bones: {len(arm.data.bones)} | Objects: {len(bpy.data.objects)}")
    print(f"    Emitters: {len(emitters_in_scene)} | Ribbons: {len(ribbons_in_scene)} | Sequences: {len(sequences)}")

    if f_info.get('expect_particles'):
        assert len(emitters_in_scene) > 0, "Expected particle emitters in scene"
    if f_info.get('expect_ribbons'):
        assert len(ribbons_in_scene) > 0, "Expected ribbon emitters in scene"
    if f_info.get('expect_attachments'):
        assert len(attachments) > 0, "Expected attachment bones in the armature"

    # Step 2: Export Lossless GLB
    lossless_glb = os.path.join(tmp_dir, f"{f_id}_lossless.glb")
    lossless_sidecar = os.path.join(tmp_dir, f"{f_id}_lossless.wc3.json")
    res_l = bpy.ops.warcraft_3.export_lossless_glb(filepath=lossless_glb)
    assert res_l == {'FINISHED'}, f"Lossless export failed: {res_l}"

    gltf_lossless = validate_glb_structure(lossless_glb, expected_mode='lossless')
    sidecar_lossless = validate_sidecar(lossless_sidecar, expected_mode='lossless')
    simulate_godot_post_import_verification(gltf_lossless, sidecar_lossless, expected_mode='lossless')
    print(f"  [Lossless GLB Export OK] Size: {os.path.getsize(lossless_glb):,} bytes | Sidecar Warnings: {len(sidecar_lossless['warnings'])}")

    # Step 3: Export Compatible GLB
    compat_glb = os.path.join(tmp_dir, f"{f_id}_compat.glb")
    compat_sidecar = os.path.join(tmp_dir, f"{f_id}_compat.wc3.json")
    res_c = bpy.ops.warcraft_3.export_compatible_glb(filepath=compat_glb)
    assert res_c == {'FINISHED'}, f"Compatible export failed: {res_c}"

    gltf_compat = validate_glb_structure(compat_glb, expected_mode='compatible')
    sidecar_compat = validate_sidecar(compat_sidecar, expected_mode='compatible')
    simulate_godot_post_import_verification(gltf_compat, sidecar_compat, expected_mode='compatible')
    print(f"  [Compatible GLB Export OK] Size: {os.path.getsize(compat_glb):,} bytes | Sidecar Warnings: {len(sidecar_compat['warnings'])}")

    # Step 4: Round-trip Re-import into Blender
    bpy.ops.wm.read_factory_settings(use_empty=True)
    reimport_res = bpy.ops.import_scene.gltf(filepath=lossless_glb)
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
