# BlenderMDX - WarCraft 3 (.mdx) Importer for Blender

[![Blender 4.2 - 5.2 LTS](https://img.shields.io/badge/Blender-4.2%20--%205.2%20LTS-orange.svg)](https://www.blender.org/)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-green.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/nphucduc203/BlenderMDX)](https://github.com/nphucduc203/BlenderMDX/releases)

A modern, high-performance addon for **Blender 4.2, 4.5, and 5.2 LTS** to import **WarCraft 3** 3D models (`.mdx`), textures (`.blp`), particle emitters, and animations with full fidelity matching Retera Model Studio and the in-game engine.

![BlenderMDX Preview](docs/preview.png)

---

## ✨ Features

- **Full MDX Chunk Support**:
  - `GEOS` & `GEOA`: Geosets, vertex groups, UV channels, normals, and geoset visibility animations.
  - `BONE` & `HELP`: Complete hierarchical skeleton with bones and helper nodes.
  - `ATCH`: Attachment points (e.g. `Hand, Left`, `Chest`, `Origin`).
  - `EVTS`: Event objects for sound cues and spell footprints.
  - `CLID`: Collision shapes for bounds and physics hitboxes.
  - `PRE2` & `RIBB`: WarCraft 3 `ParticleEmitter2` and Ribbon emitters.
  - `TXAN` & `GLBS`: Texture coordinate animations (`TVertexAnims`) and global sequences.
  - `CAMS`: Model cameras imported as Blender cameras (with animated target empty, Track To constraint, and FOV → focal length animation).
  - `LITE`: Omnidirectional/directional lights parented into the bone hierarchy, with animated color and intensity.
  - **Reforged Compatibility**: accepts MDX version 800 *and* 1000, and skips Reforged-only chunks (`CORN`, `BORN`, `FAFX`) gracefully.

- **High-Fidelity Texturing & Shading**:
  - Direct native `.blp` image decoding (JPEG & DXT1/DXT3/DXT5 compressed BLP formats).
  - Eliminates black outlines around semi-transparent edges using separate alpha and RGB color math.
  - **Multi-Layer Additive Materials**: Seamlessly layers additive textures (e.g. animated star shimmers, galaxy cloaks) over base diffuse surfaces with real-time UV translation.

- **WarCraft 3 `ParticleEmitter2` Conversion**:
  - Converts WC3 particle emitters into native Blender particle systems in the `"WarCraft 3 Particles"` collection.
  - Zero-gravity setting (`gravity = 0.0`) ensures aura and paw effects hover and swirl naturally rather than falling like snow.
  - Age/Lifetime color fades driven by `ShaderNodeParticleInfo` matching `segment_colors` and `segment_alphas`.
  - Dynamic GPU-driven UV flipbook shaders for animated particle sheets (e.g. 4x4 fire, 2x2 star bursts).

- **Animation Sequence Controller**:
  - Dedicated **WarCraft 3** tab in the 3D Viewport sidebar (`N` panel) listing all model sequences (`Stand`, `Walk`, `Attack`, `Spell`, `Death`, etc.).
  - Isolated action naming and automatic purging of orphaned actions, preventing animation collisions when deleting objects or importing multiple models.

- **Godot Engine (.glb) Export**:
  - One-click exporter to Godot-ready `.glb` format with embedded textures and NLA animation tracks.

---

## 🚀 Installation

### Option 1: Release ZIP (Recommended)
1. Download `io_scene_warcraft_3.zip` from the [Latest Release](https://github.com/nphucduc203/BlenderMDX/releases/latest).
2. Open **Blender** (version 4.2 or newer, including 5.2 LTS).
3. Go to **Edit** > **Preferences** > **Add-ons**.
4. Click the downward arrow in the top right and choose **Install from Disk...**.
5. Select the downloaded `io_scene_warcraft_3.zip` file.
6. Enable the checkbox for **WarCraft 3 .mdx importer**.

### Option 2: Manual Installation via Git
Clone this repository directly and copy the `io_scene_warcraft_3` folder into your Blender addons directory:

```bash
git clone https://github.com/nphucduc203/BlenderMDX.git
```

**Addons path on Windows:**
```
%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\io_scene_warcraft_3
```

---

## 🎮 Usage

1. In Blender, navigate to **File** > **Import** > **WarCraft 3 (.mdx)**.
2. Select your `.mdx` file.
3. Configure import options in the right-hand panel:
   - **Auto Import Textures (.blp)**: Automatically search for `.blp` files in the model's directory or subfolders.
   - **Convert Particle Emitters**: Convert `ParticleEmitter2` nodes into Blender particle systems.
   - **Global Scale**: Default is `0.03` (optimal for Warcraft III scale in Blender).
   - **Team Color**: Choose player team color (Red, Blue, Teal, Purple, etc.).
4. Click **Import WarCraft 3 (.mdx)**.

### Switching Animations
1. Select the model's Armature.
2. Open the Sidebar by pressing `N` in the 3D Viewport.
3. Switch to the **WarCraft 3** tab.
4. Click any sequence in the **Animation Sequences** list to play!

---

## 📋 Changelog

### v1.4.1
- **Godot GLB export rewritten**: the exporter now exports only the model itself (armature + meshes + camera/lights) instead of the whole scene, so Blender-side particle preview helpers (`W3_Inst_*` quads at −1000, `W3_Emitter_*`) and unrelated scene objects no longer leak into the GLB.
- **Textures survive glTF export**: WC3 materials use ObjectInfo tints and Add-Shader emission that the glTF exporter cannot translate (re-imported models rendered black/untextured). Export now temporarily swaps in flat `texture → Base Color / Alpha / Emission` materials and restores your originals afterwards.
- **Cameras exported** (`export_cameras`): MDX cameras and their FOV animation now reach Godot.
- Round-trip verified: re-importing the exported GLB shows all 12 sequences, the camera, and correctly textured meshes (tiger mount no longer black).

> **Previewing exported GLBs in Blender**: Blender's glTF importer draws every bone with a stretched octahedron and an Icosphere custom shape — this is a *display artifact of the importer*, not part of the file, and Godot does not show it. Press **Fix glTF Display (Hide Spheres)** in the WarCraft 3 sidebar tab to clean the viewport.

### v1.4.0
- **Reforged MDX Support (VERS 1000)**: files saved by WarCraft 3: Reforged tools now import; unknown versions warn instead of aborting.
- **Global Sequences (GLBS)**: tracks bound to a global sequence are loop-unrolled into every animation sequence instead of being dropped or mis-shifted.
- **Cameras (`CAMS`)**: imported as Blender cameras with target empty + Track To constraint, animated position/target, and FOV animation converted to focal length.
- **Lights (`LITE`)**: imported as Blender lights attached to their node bone, with animated color and intensity that follow sequence switching.
- **Crash Fix**: hardened custom split-normals import against a Blender 5.x crash (zero-length normals + session state previously killed Blender on models like SalvationSpire). Verified importing 148 models back-to-back without a crash.
- **Attachment visibility (`KATV`) and event tracks (`KEVT`)** are now parsed and stored instead of discarded.
- **Safer Cleanup**: orphaned-action purging now only touches actions created by this addon, never the user's own actions.
- **Lighter Files**: nodes without any animation no longer get placeholder fcurves in every action (fewer fcurves/keyframes, identical playback).
- **Parser Hardening**: unknown sub-chunks inside layers, nodes, and geoset animations resync instead of raising; `.mdl` files produce a clear conversion hint.
- **Compatibility**: verified on Blender 5.2.2 LTS (Python 3.13) and 4.2+.

> **Note**: `.mdl` (text format) is not supported — convert to `.mdx` with Retera Model Studio first.

### v1.3.0
- **Multi-layer Additive Texture Support**: Fully supports Material Layer 2 with Additive blending and dynamic `TVertexAnims` UV animation (e.g. `2 (95)_8.blp` star shimmer on wings).
- **Accurate ParticleEmitter2 System**: Zero-gravity floating particles, Age/Lifetime color fades, and UV flipbooks.
- **Particle UI Controls**: Added **Convert WC3 Particle Emitters** and **Toggle Particle Visibility** buttons in the sidebar.
- **Cross-File Animation Bug Fix**: Isolated actions by Armature and automatically purged orphaned actions upon deletion and re-import.
- **Compatibility**: Verified compatibility with Blender 5.2 LTS and Python 3.12.

---

## 👥 Credits & Acknowledgements

- **Pavel_Blend**: Original creator of the Blender 2.79 Warcraft 3 importer.
- **Torenjk**: Modernization for Blender 4.x.
- **Retera**: Author of [Retera Model Studio](https://github.com/Retera/ReterasModelStudio), the gold standard reference for Warcraft 3 MDX/MDL modeling.
- **flowtsohg**: Author of [mdx-m3-viewer](https://github.com/flowtsohg/mdx-m3-viewer).
- **DrSuperGood**: Author of [blp-iio-plugin](https://github.com/DrSuperGood/blp-iio-plugin).

---

## 📄 License

This project is licensed under the [BSD 2-Clause License](LICENSE) and compatible with Blender's GPL licensing.
