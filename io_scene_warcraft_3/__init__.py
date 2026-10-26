bl_info = {
    'name': 'WarCraft 3 .mdx Importer & Game Engine .glb Exporter',
    'author': 'nphucduc203, Torenjk, Pavel_Blend, Nekuromu',
    'version': (1, 7, 0),
    'blender': (4, 2, 0),
    'category': 'Import-Export',
    'location': 'File > Import / Export',
    'description': 'Import WarCraft 3 *.mdx / *.mdl models and export full multi-layer *.glb for Godot, Unity, Unreal & Blender 5.2',
    'wiki_url': 'https://github.com/nphucduc203/BlenderMDX',
    'tracker_url': 'https://github.com/nphucduc203/BlenderMDX/issues'
}

import importlib
from . import (
    constants,
    classes,
    binary,
    blp,
    utils,
    types,
    preferences,
    importer,
    mdl,
    parser,
    operators,
    ui,
    plugin,
)

for _mod in (
    constants,
    classes,
    binary,
    blp,
    utils,
    types,
    preferences,
    importer,
    mdl,
    parser,
    operators,
    ui,
    plugin,
):
    try:
        importlib.reload(_mod)
    except Exception:
        pass

from .plugin import register, unregister
