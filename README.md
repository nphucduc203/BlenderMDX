# BlenderMDX - WarCraft 3 (.mdx) Importer for Blender

[![Blender 4.2 - 5.2 LTS](https://img.shields.io/badge/Blender-4.2%20--%205.2%20LTS-orange.svg)](https://www.blender.org/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
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
