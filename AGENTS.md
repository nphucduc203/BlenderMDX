# BlenderMDX - Agent Guidelines

## Overview
BlenderMDX is a high-performance Blender addon (**Blender 4.2 - 5.2 LTS**) to import WarCraft 3 models (`.mdx`), textures (`.blp`), particle systems, and animation sequences, plus a 2-tier `.glb` exporter for game engines (Godot, Unity, Unreal). The repository also includes standalone Godot 4 post-import tools and an editor addon.

---

## Directory Structure
- `io_scene_warcraft_3/`: Core Blender addon package.
  - `__init__.py`: Addon entry point (`bl_info` metadata, registration loop).
  - `blender_manifest.toml`: Extension manifest required by Blender 4.2+ extensions platform.
  - `parser.py`: Binary MDX chunk deserializer (`GEOS`, `BONE`, `HELP`, `ATCH`, `EVTS`, `CLID`, `PRE2`, `RIBB`, `TXAN`, `GLBS`, `CAMS`, `LITE`).
  - `mdl.py`: Text `.mdl` parser producing the same `WarCraft3Model` as `parser.py`; `parser.load_mdx()` picks the format from the file header.
  - `binary.py`: Binary stream reader and low-level glTF 2.0 binary GLB postprocessor (`postprocess_wc3_glb`).
  - `blp.py`: Pure-Python `.blp` image decoder supporting both JPEG and DXT1/DXT3/DXT5 compression formats.
  - `importer.py`: Scene generation (mesh geometry, split normals, materials, bone hierarchy, actions, particles, cameras, lights).
  - `operators.py`: UI operators (`bpy.types.Operator`), GLB export pipelines, sequence playback, and display fixes.
  - `ui.py`: 3D Viewport sidebar panel (`VIEW_3D` -> `UI` -> **WarCraft 3** tab).
  - `classes.py`, `constants.py`, `types.py`, `utils.py`, `preferences.py`: Data models, chunk IDs, and helpers.
- `godot_tools/`: Companion scripts for Godot 4 projects importing exported GLB files:
  - `wc3_post_import.gd`: `EditorScenePostImport` script restoring additive blend materials and spawning `GPUParticles3D` on bones.
  - `wc3_additive.gdshader`: Spatial shader for true additive blending.
- `godot_addon/warcraft_3_mdx/`: Standalone Godot 4 editor plugin for direct drag-and-drop `.mdx` / `.blp` import.
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

### 2. 2-Tier GLB Export Architecture
- **Lossless GLB (`WARCRAFT_3_OT_export_lossless_glb`)**:
  - Splits multi-layer geosets into multiple glTF primitives within a single mesh.
  - Preserves exact `layerAlpha`, tint color, and `wc3_blend: "additive"` metadata in glTF `extras`.
  - Exports particle emitter markers (`W3_Emitter_*`) parented to bones carrying emitter parameters in `extras`.
- **Compatible GLB (`WARCRAFT_3_OT_export_compatible_glb`)**:
  - Standard glTF PBR approximation (`layerAlpha²` + boosted emission via `KHR_materials_emissive_strength`) for universal viewers (Windows 3D Viewer, web).
- **Material Swap & Restore**:
  - Export temporarily flattens WC3 custom node graphs into standard glTF-compatible materials.
  - **Crucial**: The original materials must always be restored in a `try...finally` block. Never leave temporary export materials attached to user scene objects.
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
