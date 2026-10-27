# BlenderMDX - Agent Guidelines

## Overview
BlenderMDX is a high-performance Blender addon (**Blender 4.2 - 5.2 LTS**) to import WarCraft 3 models (`.mdx` binary and `.mdl` text), textures (`.blp`), particle systems, and animation sequences, plus a single engine-ready `.glb` exporter (standard glTF 2.0 with `wc3_*` extras).

---

## Directory Structure
- `io_scene_warcraft_3/`: Core Blender addon package.
  - `__init__.py`: Addon entry point (`bl_info` metadata, registration loop).
  - `blender_manifest.toml`: Extension manifest required by Blender 4.2+ extensions platform.
  - `parser.py`: Binary MDX chunk deserializer (`GEOS`, `BONE`, `HELP`, `ATCH`, `EVTS`, `CLID`, `PRE2`, `RIBB`, `TXAN`, `GLBS`, `CAMS`, `LITE`).
  - `mdl.py`: Text `.mdl` parser producing the same `WarCraft3Model` as `parser.py`; `parser.load_mdx()` picks the format from the file header.
  - `binary.py`: Low-level binary stream reader (`Reader`) used by both parsers.
  - `blp.py`: Pure-Python `.blp` image decoder supporting both JPEG and DXT1/DXT3/DXT5 compression formats.
  - `importer.py`: Scene generation (mesh geometry, split normals, materials, bone hierarchy, actions, particles, cameras, lights).
  - `operators.py`: UI operators (`bpy.types.Operator`), the single `.glb` exporter plus the `postprocess_wc3_glb()` glTF JSON-chunk fixer, sequence playback, and display fixes.
  - `ui.py`: 3D Viewport sidebar panel (`VIEW_3D` -> `UI` -> **WarCraft 3** tab).
  - `classes.py`, `constants.py`, `types.py`, `utils.py`, `preferences.py`: Data models, chunk IDs, and helpers.
- `tools/wc3_glb_viewer/`: Godot 4 viewer scene (`viewer.tscn` + `viewer.gd`) for opening an exported `.glb` and cycling its animations; copy the folder into a Godot project to use. Not part of the addon package.
- `docs/`: Documentation assets (previews, screenshots).

---

## Verification & Build Commands

### 1. Python Syntax & Compilation Check
Verify all addon files compile without syntax errors:
```bash
python -m py_compile io_scene_warcraft_3/*.py
```

### 2. Headless Blender Addon Registration Test
Run registration and unregistration cleanly in Blender 5.2 headless mode:
```bash
"D:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --python-expr "import sys; sys.path.insert(0, '.'); import io_scene_warcraft_3; io_scene_warcraft_3.register(); io_scene_warcraft_3.unregister()"
```

### 3. Build Release Addon ZIP
Package the addon into `io_scene_warcraft_3.zip` excluding `__pycache__`:
```bash
python -c "import zipfile, os; z=zipfile.ZipFile('io_scene_warcraft_3.zip','w',zipfile.ZIP_DEFLATED); [z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f),'.')) for r,_,fs in os.walk('io_scene_warcraft_3') if '__pycache__' not in r for f in fs]; z.close()"
```

---

## Architectural Boundaries & Key Rules

### 1. Dual Version Manifest Synchronization
Whenever modifying or bumping the version, **always update both files synchronously**:
1. `io_scene_warcraft_3/__init__.py`: `bl_info['version'] = (x, y, z)`
2. `io_scene_warcraft_3/blender_manifest.toml`: `version = "x.y.z"`

### 2. Single Engine-Ready GLB Export (`WARCRAFT_3_OT_export_glb`, `warcraft_3.export_glb`)
- One `.glb` per model, standard glTF 2.0 so any engine can open it without companion code:
  - Splits multi-layer geosets into multiple glTF primitives within a single mesh.
  - Preserves exact `layerAlpha`, tint color, and `wc3_blend: "additive"` metadata in glTF `extras` (glTF itself has no additive mode).
  - Exports particle emitter markers (`W3_Emitter_*`) parented to bones carrying emitter parameters in `extras`.
  - One glTF animation per WarCraft 3 sequence (`export_animation_mode='ACTIONS'`).
  - Additive layers (`filter_mode` 3/4) export a luminance-alpha copy of their texture (`_additive_mask_image`, image name `<texture>_addmask`) because glTF cannot express additive blending and WC3 additive textures keep an opaque-black alpha channel that would darken the background in a stock alpha-blend engine. The copies are purged after the export.
  - `export_animation_mode='ACTIONS'` exports every action in the .blend (other models included), so `postprocess_wc3_glb(keep_animations=...)` strips every animation not tagged `wc3_armature_name == <exported armature>`.
- There is deliberately **no** second "compatible" tier and **no** Godot/Unity post-import script in this repo; engines read `extras` if they want exact blending.
- **Material Swap & Restore**:
  - Export temporarily flattens WC3 custom node graphs into standard glTF-compatible materials.
  - **Crucial**: The original materials must always be restored in a `try...finally` block. Never leave temporary export materials attached to user scene objects.
- **Layer Animation Contract**: `create_warcraft3_material` names each alpha multiplier node `LayerAlpha_Mat{material}_L{layer}` and records the real layer→node mapping in `model.alpha_node_map` (runtime attribute, never a material property, so it stays out of glTF `extras`); `animate_material_layers` reads that map — a team-color merge moves layer 1's alpha onto the `_L0` node, so index guessing misses it. `make_action_cyclic`/`_iter_action_fcurves` are the only sanctioned way to walk fcurves (Blender <= 4.3 `action.fcurves` vs 4.4+ layer/channelbag nesting).
- **Binary Postprocessing**:
  - `postprocess_wc3_glb()` enforces glTF 2.0 material properties directly into the exported `.glb` binary chunks and guarantees strict 4-byte alignment.

### 3. Animation Sequences & Action Isolation
- MDX animations are stored as distinct Blender Actions with prefixed names (`_new_tagged_action`).
- `purge_orphaned_wc3_actions()` must **only** purge actions tagged with this addon's naming schema; never delete user-created actions.
- Switching sequences via the sidebar N-panel pushes active tracks cleanly without cross-contaminating NLA tracks.

### 4. Geometry & Normal Robustness
- In Blender 5.x, custom split normals must guard against zero-length vectors and invalid loops to prevent native engine crashes.
- Support both MDX version 800 (classic) and 1000 (Reforged). Safely ignore unsupported Reforged chunks (`CORN`, `BORN`, `FAFX`). Reforged-only *fields* (256-byte MODL name, `MTLS` shader name, layer emissive/fresnel) are still not read — classic field offsets are assumed after `VERS`.
- Text `.mdl` files are imported by `mdl.py`, which must keep producing the *same* `WarCraft3Model` as `parser.py` (no format-specific branches in `importer.py`). Colors: `.mdl` literals are BGR, `.mdx` `GEOA` static color is RGB and only the `KGAC` track is BGR.

### 5. Dependency & Environment Constraints
- The Blender addon must strictly use Python standard library and Blender APIs (`bpy`, `bmesh`, `mathutils`, `bpy_extras`). **Do not add third-party pip dependencies** to `io_scene_warcraft_3/`.
- Adhere to the `ponytail` standard: choose the minimal complete solution, reuse existing helpers, and mark intentional shortcuts with `shortcut:`.
