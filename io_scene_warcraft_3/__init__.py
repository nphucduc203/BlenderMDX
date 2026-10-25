
bl_info = {
    'name': 'WarCraft 3 .mdx importer',
    'author': 'nphucduc203, Torenjk, Pavel_Blend, Nekuromu',
    'version': (1, 4, 3),
    'blender': (4, 2, 0),
    'category': 'Import-Export',
    'location': 'File > Import',
    'description': 'Import *.mdx files (3d models of WarCraft 3)',
    'wiki_url': 'https://github.com/nphucduc203/BlenderMDX',
    'tracker_url': 'https://github.com/nphucduc203/BlenderMDX/issues'
}


from .plugin import register, unregister
