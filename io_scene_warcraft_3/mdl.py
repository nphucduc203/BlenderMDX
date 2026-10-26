"""Text .mdl parser producing the same WarCraft3Model the binary .mdx parser emits.

Grammar follows github.com/MrMoonKr/war3-model (mdl/parse.ts + mdl/generate.ts, MIT).
Values land in the addon's internal conventions (wxyz quats, flipped UV v) so importer.py
needs no format-specific branches.

MDL color literals are BGR (binary MDX and Blender are RGB), so color values are reversed
while parsing; SegmentColor entries nest their value in a `Color { r g b }` block.
"""

import re

from . import classes
from . import constants

SHADING_FLAGS = {
    'Unshaded': 0x1, 'SphereEnvMap': 0x2, 'TwoSided': 0x10,
    'Unfogged': 0x20, 'NoDepthTest': 0x40, 'NoDepthSet': 0x80,
}

NODE_FLAGS = {
    'Billboarded': 0x8, 'BillboardedLockX': 0x10, 'BillboardedLockY': 0x20,
    'BillboardedLockZ': 0x40, 'CameraAnchored': 0x80,
}

DONT_INHERIT_FLAGS = {'Translation': 0x1, 'Rotation': 0x2, 'Scaling': 0x4}

TEXTURE_FLAGS = {'WrapWidth': 1, 'WrapHeight': 2}

FILTER_MODES = {'None': 0, 'Transparent': 1, 'Blend': 2, 'Additive': 3,
                'AddAlpha': 4, 'Modulate': 5, 'Modulate2x': 6}

MATERIAL_FLAGS = {'ConstantColor': 1, 'SortPrimsFarZ': 16, 'FullResolution': 32}

GEOSET_ANIM_FLAGS = {'DropShadow': 1}

PE2_FILTER_MODES = {'Blend': 0, 'Additive': 1, 'Modulate': 2, 'Modulate2x': 3, 'AlphaKey': 4}

PE2_FRAME_FLAGS = {'Head': 0, 'Tail': 1, 'Both': 2}

LINE_TYPES = {'DontInterp': 0, 'Linear': 1, 'Hermite': 2, 'Bezier': 3}

LIGHT_TYPES = {'Omnidirectional': 0, 'Directional': 1, 'Ambient': 2}

SHAPE_TYPES = {'Box': 0, 'Cylinder': 1, 'Sphere': 2}

# Keywords that act as a property *value* rather than as a standalone boolean flag.
VALUE_KEYWORDS = frozenset(FILTER_MODES) | frozenset(PE2_FILTER_MODES) | {'Multiple'}

NO_GEOSET = 0xffffffff

_TOKEN_RE = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|[^A-Za-z0-9+.\-"{},:]+|"(?P<str>[^"]*)"|'
                       r'(?P<kw>[A-Za-z][A-Za-z0-9]*)|(?P<sym>[{}:])|'
                       r'(?P<num>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)')


class MDLParseError(Exception):
    pass


class _Tokens:
    def __init__(self, text):
        self.items = []
        pos = 0
        while pos < len(text):
            match = _TOKEN_RE.match(text, pos)
            if not match:
                pos += 1
                continue
            pos = match.end()
            string, keyword, sym, num = match.group('str', 'kw', 'sym', 'num')
            if string is not None:
                self.items.append(('str', string))
            elif keyword is not None:
                self.items.append(('kw', keyword))
            elif sym is not None:
                self.items.append(('sym', sym))
            elif num is not None:
                self.items.append(('num', float(num)))
        self.pos = 0

    def peek(self, offset=0):
        index = self.pos + offset
        return self.items[index] if 0 <= index < len(self.items) else (None, None)

    def at_end(self):
        return self.pos >= len(self.items)

    def take(self):
        item = self.peek()
        if item[0] is None:
            raise MDLParseError('unexpected end of file')
        self.pos += 1
        return item

    def is_kw(self, value, offset=0):
        return self.peek(offset) == ('kw', value)

    def is_sym(self, value):
        return self.peek() == ('sym', value)


def _num(t):
    kind, value = t.take()
    if kind != 'num':
        raise MDLParseError('expected a number, got {0!r}'.format(value))
    return value


def _int(t):
    return int(round(_num(t)))


def _str(t):
    kind, value = t.take()
    if kind != 'str':
        raise MDLParseError('expected a quoted string, got {0!r}'.format(value))
    return value


def _kw(t):
    kind, value = t.take()
    if kind != 'kw':
        raise MDLParseError('expected a keyword, got {0!r}'.format(value))
    return value


def _open(t):
    if not t.is_sym('{'):
        raise MDLParseError('expected a block, got {0!r}'.format(t.peek()[1]))
    t.pos += 1


def _close(t):
    if t.is_sym('}'):
        t.pos += 1
        return True
    return False


def _counts(t):
    """Enter `Keyword n m { ... }`, returning the numbers that preceded the brace.

    They are element counts, redundant with the braces, so callers may ignore them.
    """
    out = []
    while t.peek()[0] == 'num':
        out.append(_int(t))
    _open(t)
    return out


def _skip_block(t):
    depth = 1
    while depth and not t.at_end():
        kind, value = t.take()
        if kind == 'sym' and value == '{':
            depth += 1
        elif kind == 'sym' and value == '}':
            depth -= 1


def _track(t):
    """<LineType>[, GlobalSeqId n], frame: value, [InTan: .., OutTan: ..] ... until the brace."""
    track = classes.WarCraft3GeosetTransformation()
    kind, value = t.peek()
    has_line_type = kind == 'kw' and value in LINE_TYPES
    # Real files omit the interpolation keyword when it is the default Linear.
    track.interpolation_type = LINE_TYPES[value] if has_line_type else 1
    if has_line_type:
        t.pos += 1
    track.global_sequence_id = None
    components = None
    while not t.at_end() and not _close(t):
        if t.is_kw('GlobalSeqId'):
            t.take()
            track.global_sequence_id = _int(t)
            continue
        if t.peek()[0] != 'num':
            t.take()
            continue
        track.times.append(_int(t))
        if t.is_sym(':'):
            t.pos += 1
        if t.is_sym('{'):
            t.pos += 1
            values = []
            while not t.at_end() and not _close(t):
                values.append(_num(t))
            if components is None:
                components = len(values)
            track.values.append(tuple(values))
        else:
            value = _num(t)
            if components is None:
                components = 1
            track.values.append(value)
        # shortcut: tangent handles are consumed and dropped (as in parser.py); Blender auto-handles them.
        while t.is_kw('InTan') or t.is_kw('OutTan'):
            t.take()
            _value(t)
    track.tracks_count = len(track.times)
    if components == 4:
        track.values = [(w, x, y, z) for (x, y, z, w) in track.values]
    return track


def _value(t):
    """Right-hand side of a property: block array, track, scalar, string or bare keyword."""
    if t.peek()[0] == 'num' and t.peek(1) == ('sym', '{'):
        t.pos += 1  # element count, redundant with the block contents
    if not t.is_sym('{'):
        kind, value = t.peek()
        if kind in ('num', 'str', 'kw'):
            t.pos += 1
        return value
    t.pos += 1
    # 'Translation { 2 { Linear, ... } }': the keyframe list sits inside a second brace pair.
    wrapper = t.peek()[0] == 'num' and t.peek(1) == ('sym', '{')
    if wrapper:
        t.pos += 2
    body = _body(t)
    if wrapper:
        _close(t)
    return body


def _body(t):
    """Contents of an already opened block: a track, a list of vectors or a flat tuple."""
    if t.peek()[0] == 'kw' and t.peek()[1] in LINE_TYPES:
        return _track(t)
    if t.peek()[0] == 'num' and t.peek(1) == ('sym', ':'):
        return _track(t)
    if t.is_sym('{'):
        items = []
        while not t.at_end() and not _close(t):
            if t.is_sym('{'):
                t.pos += 1
                items.append(tuple(_numbers(t)))
            else:
                t.take()
        return items
    return tuple(_numbers(t))


def _numbers(t):
    """Numbers up to the closing brace of the block _value just entered."""
    out = []
    while not t.at_end() and not _close(t):
        if t.peek()[0] == 'num':
            out.append(_num(t))
        else:
            t.take()
    return out


def _flat_numbers(t):
    """Numbers inside nested braces at any depth, up to and including the closing brace."""
    out = []
    while not t.at_end() and not _close(t):
        if t.is_sym('{'):
            t.pos += 1
            out.extend(_flat_numbers(t))
        elif t.peek()[0] == 'num':
            out.append(_int(t))
        else:
            t.take()
    return out


def _rgb(value):
    """Swap an MDL BGR color or color track to RGB."""
    if isinstance(value, classes.WarCraft3GeosetTransformation):
        value.values = [tuple(reversed(v)) if isinstance(v, tuple) and len(v) == 3 else v
                        for v in value.values]
        return value
    if isinstance(value, tuple) and len(value) == 3:
        return tuple(reversed(value))
    return value


def _scalar(value, default):
    """Collapse whatever _value produced into a single Python value."""
    if value is None:
        return default
    if isinstance(value, classes.WarCraft3GeosetTransformation):
        return _scalar(value.values[0], default) if value.values else default
    if isinstance(value, tuple) and len(value) == 3:
        return value
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _props(t, node=None):
    """Parse a `Keyword { ... }` body into (node, props). Unknown keywords are collected."""
    props = {}
    while not t.at_end() and not _close(t):
        kind, value = t.peek()
        if kind == 'sym':
            t.take()
            continue
        if kind != 'kw':
            t.take()
            continue
        keyword = _kw(t)
        if node is not None:
            if keyword == 'ObjectId':
                node.id = int(_scalar(_value(t), node.id))
                continue
            if keyword == 'Parent':
                parent = _scalar(_value(t), -1)
                node.parent = None if not isinstance(parent, (int, float)) or parent < 0 else int(parent)
                continue
            if keyword in ('Translation', 'Rotation', 'Scaling'):
                setattr(node, keyword.lower() + 's', _value(t))
                continue
            if keyword == 'DontInherit':
                _open(t)
                while not _close(t):
                    node.flags |= DONT_INHERIT_FLAGS.get(_kw(t), 0)
                continue
            if keyword in NODE_FLAGS:
                node.flags |= NODE_FLAGS[keyword]
                continue
        if keyword == 'Layer' and t.is_sym('{'):
            t.pos += 1
            props.setdefault('Layers', []).append(_parse_layer(t))
            continue
        if keyword in ('Particle', 'Target') and t.is_sym('{'):
            t.pos += 1
            props[keyword] = _props(t)[1]
            continue
        if keyword == 'SegmentColor' and t.is_sym('{'):
            t.pos += 1
            colors = []
            while not t.at_end() and not _close(t):
                if t.peek()[0] == 'kw':
                    t.take()    # 'Color'
                elif t.is_sym('{'):
                    t.pos += 1
                    colors.append(_rgb(tuple(_numbers(t))))
                else:
                    t.take()
            props[keyword] = colors
            continue
        if keyword == 'static':
            continue
        kind, value = t.peek()
        if kind in ('num', 'str') or value == '{' or (kind == 'kw' and value in VALUE_KEYWORDS):
            parsed = _value(t)
            props[keyword] = _rgb(parsed) if keyword in ('Color', 'AmbColor') else parsed
        else:
            props[keyword] = True
    return node, props


def _parse_layer(t):
    layer = classes.WarCraft3Layer()
    _, props = _props(t)
    layer.filter_mode = FILTER_MODES.get(props.get('FilterMode'), 0)
    if isinstance(props.get('FilterMode'), int):
        layer.filter_mode = props['FilterMode']
    alpha = props.get('Alpha')
    if isinstance(alpha, classes.WarCraft3GeosetTransformation):
        layer.material_alpha = alpha
        layer.alpha = _scalar(alpha, 1.0)
    else:
        layer.alpha = _scalar(alpha, 1.0)
    texture_id = props.get('TextureID')
    if isinstance(texture_id, classes.WarCraft3GeosetTransformation):
        layer.material_texture_id = texture_id
        layer.texture_id = int(_scalar(texture_id, 0))
    else:
        layer.texture_id = int(_scalar(texture_id, 0))
    layer.coord_id = int(_scalar(props.get('CoordId'), 0))
    animation_id = props.get('TVertexAnimId')
    layer.texture_animation_id = None if animation_id is None else int(_scalar(animation_id, 0))
    for keyword, bit in SHADING_FLAGS.items():
        if props.get(keyword):
            layer.shading_flags |= bit
    return layer


def _parse_geoset(t, model):
    from . import parser as mdx_parser
    mesh = classes.WarCraft3Mesh()
    mesh.vertex_groups_ids = []    # importer iterates this even for a geoset without a Groups block
    vertex_group = None
    groups = None
    while not t.at_end() and not _close(t):
        kind, value = t.peek()
        if kind != 'kw':
            t.take()
            continue
        keyword = _kw(t)
        if keyword in ('Vertices', 'Normals', 'TVertices'):
            components = 2 if keyword == 'TVertices' else 3
            _counts(t)
            values = []
            while not t.at_end() and not _close(t):
                if t.peek()[0] == 'num' or t.is_sym('{'):
                    vec = _vec(t, components)
                    values.append((vec[0], 1.0 - vec[1]) if keyword == 'TVertices' else vec)
                else:
                    t.take()
            if keyword == 'Vertices':
                mesh.vertices = values
            elif keyword == 'Normals':
                mesh.normals = values
            else:
                mesh.uv_sets.append(values)
        elif keyword == 'VertexGroup':
            _counts(t)
            vertex_group = []
            while not t.at_end() and not _close(t):
                if t.peek()[0] == 'num':
                    vertex_group.append(_int(t))
                else:
                    t.take()
        elif keyword == 'Groups':
            counts = _counts(t)
            matrices = [[] for _ in range(counts[0] if counts else 0)]
            group_index = 0
            while not t.at_end() and not _close(t):
                if t.is_kw('Matrices'):
                    t.take()
                if t.is_sym('{') or (t.peek()[0] == 'num' and t.peek(1) == ('sym', '{')):
                    if group_index < len(matrices):
                        matrices[group_index] = [int(v) for v in _value(t)]
                    else:
                        _value(t)
                    group_index += 1
                else:
                    t.take()
            groups = matrices
        elif keyword == 'Faces':
            _counts(t)
            indices = _flat_numbers(t)
            mesh.triangles.extend(tuple(indices[i:i + 3]) for i in range(0, len(indices) - 2, 3))
        elif keyword == 'MaterialID':
            mesh.material_id = int(_scalar(_value(t), 0))
        elif keyword == 'SelectionGroup':
            mesh.selection_group = int(_scalar(_value(t), 0))
        elif keyword == 'Unselectable':
            mesh.selection_flags = 1
        else:
            if t.peek()[0] == 'num' and t.peek(1) == ('sym', '{'):
                t.take()
            if t.is_sym('{'):
                t.pos += 1
                _skip_block(t)    # 'Anim { ... }' has no WarCraft3Mesh representation
            else:
                _value(t)
    if mesh.uv_sets:
        mesh.uvs = mesh.uv_sets[0]
    if groups is not None and vertex_group is not None:
        mesh.vertex_groups, mesh.vertex_groups_ids = mdx_parser.get_vertex_groups(
            vertex_group, [len(m) for m in groups], [i for m in groups for i in m])
    model.meshes.append(mesh)


def _vec(t, count):
    if t.is_sym('{'):
        t.pos += 1
        out = tuple(_num(t) for _ in range(count))
        while t.peek()[0] == 'num':
            _num(t)
        if t.is_sym('}'):
            t.pos += 1
        return out
    return tuple(_num(t) for _ in range(count))


def _parse_geoset_anim(t, model):
    _, props = _props(t)
    anim = classes.WarCraft3GeosetAnimation()
    anim.geoset_id = NO_GEOSET
    geoset_id = props.get('GeosetId')
    if isinstance(geoset_id, (int, float)):
        anim.geoset_id = int(geoset_id)
    alpha = props.get('Alpha')
    anim.animation_alpha = alpha if isinstance(alpha, classes.WarCraft3GeosetTransformation) else None
    anim.alpha = _scalar(alpha, 1.0)
    color = props.get('Color')
    anim.animation_color = color if isinstance(color, classes.WarCraft3GeosetTransformation) else None
    anim.color = _scalar(color, (1.0, 1.0, 1.0))
    if not isinstance(anim.color, tuple):
        anim.color = (1.0, 1.0, 1.0)
    flags = 0
    if props.get('DropShadow'):
        flags |= GEOSET_ANIM_FLAGS['DropShadow']
    if anim.animation_color is not None or (isinstance(color, tuple) and color != (1.0, 1.0, 1.0)):
        flags |= 2
    anim.flags = flags
    if anim.animation_alpha is None:
        anim.animation_alpha = _constant_track(anim.alpha)
    if anim.animation_color is None:
        anim.animation_color = _constant_track(anim.color)
    model.geoset_animations.append(anim)


def _constant_track(value):
    track = classes.WarCraft3GeosetTransformation()
    track.tracks_count = 1
    track.interpolation_type = constants.INTERPOLATION_TYPE_NONE
    track.times = [0]
    track.values = [value]
    return track


def _node_owner(t, model, cls, name):
    node = classes.WarCraft3Node()
    node.name = name
    node.id = len(model.nodes)
    node.parent = None
    node.flags = 0
    _, props = _props(t, node)
    owner = cls()
    owner.node = node
    return owner, props


def _parse_bone(t, model, name):
    bone, props = _node_owner(t, model, classes.WarCraft3Bone, name)
    # 'Multiple' and 'None' both mean the MDX 0xffffffff, which parser.py stores as None.
    for attribute, key in (('geoset_id', 'GeosetId'), ('geoset_animation_id', 'GeosetAnimId')):
        value = _scalar(props.get(key), None)
        setattr(bone, attribute, int(value) if isinstance(value, (int, float)) else None)
    model.nodes.append(bone)


def _parse_helper(t, model, name):
    helper, _ = _node_owner(t, model, classes.WarCraft3Helper, name)
    model.nodes.append(helper)


def _parse_attachment(t, model, name):
    attachment, props = _node_owner(t, model, classes.WarCraft3Attachment, name)
    path = props.get('Path')
    attachment.path = path if isinstance(path, str) else ''
    attachment.attachment_id = int(_scalar(props.get('AttachmentID'), 0))
    visibility = props.get('Visibility')
    attachment.visibility = visibility if isinstance(
        visibility, classes.WarCraft3GeosetTransformation) else None
    model.nodes.append(attachment)


def _parse_event(t, model, name):
    event, props = _node_owner(t, model, classes.WarCraft3Event, name)
    tracks = props.get('EventTrack')
    event.tracks = [int(v) for v in tracks] if isinstance(tracks, (list, tuple)) else []
    model.nodes.append(event)


def _parse_collision_shape(t, model, name):
    shape, props = _node_owner(t, model, classes.WarCraft3CollisionShape, name)
    for keyword, kind in SHAPE_TYPES.items():
        if props.get(keyword):
            shape.shape_type = kind
    vertices = props.get('Vertices')
    if isinstance(vertices, (list, tuple)):
        shape.vertices = [tuple(v) if isinstance(v, (list, tuple)) else v for v in vertices]
    shape.bounds_radius = float(_scalar(props.get('BoundsRadius'), 0.0))
    model.nodes.append(shape)


def _parse_particle_emitter(t, model, name):
    emitter, props = _node_owner(t, model, classes.WarCraft3ParticleEmitter, name)
    for attr, key in (('emission_rate', 'EmissionRate'), ('gravity', 'Gravity'),
                      ('longitude', 'Longitude'), ('latitude', 'Latitude')):
        setattr(emitter, attr, float(_scalar(props.get(key), 0.0)))
    particle = props.get('Particle') or {}
    path = particle.get('Path')
    emitter.path = path if isinstance(path, str) else ''
    emitter.life_span = float(_scalar(particle.get('LifeSpan'), 0.0))
    emitter.speed = float(_scalar(particle.get('InitVelocity'), 0.0))
    model.nodes.append(emitter)
    model.particle_emitters.append(emitter)


def _parse_particle_emitter_2(t, model, name):
    emitter, props = _node_owner(t, model, classes.WarCraft3ParticleEmitter2, name)
    for attr, key in (('speed', 'Speed'), ('variation', 'Variation'), ('latitude', 'Latitude'),
                      ('gravity', 'Gravity'), ('life_span', 'LifeSpan'), ('width', 'Width'),
                      ('length', 'Length'), ('tail_length', 'TailLength'), ('time_middle', 'Time')):
        setattr(emitter, attr, float(_scalar(props.get(key), getattr(emitter, attr))))
    emission = props.get('EmissionRate')
    if isinstance(emission, classes.WarCraft3GeosetTransformation):
        emitter.emission_rate_track = emission
    emitter.emission_rate = float(_scalar(emission, emitter.emission_rate))
    visibility = props.get('Visibility')
    if isinstance(visibility, classes.WarCraft3GeosetTransformation):
        emitter.visibility_track = visibility
    filter_mode = props.get('FilterMode')
    if isinstance(filter_mode, str):
        emitter.filter_mode = PE2_FILTER_MODES.get(filter_mode, emitter.filter_mode)
    elif isinstance(filter_mode, (int, float)) and not isinstance(filter_mode, bool):
        emitter.filter_mode = int(filter_mode)
    else:
        # Classic MDL writes the emitter filter mode as a bare keyword: "Additive," "AlphaKey," ...
        for keyword, mode in PE2_FILTER_MODES.items():
            if props.get(keyword):
                emitter.filter_mode = mode
    emitter.rows = int(_scalar(props.get('Rows'), emitter.rows))
    emitter.columns = int(_scalar(props.get('Columns'), emitter.columns))
    for keyword, mode in PE2_FRAME_FLAGS.items():
        if props.get(keyword):
            emitter.head_or_tail = mode
    colors = props.get('SegmentColor')
    if isinstance(colors, (list, tuple)) and colors and isinstance(colors[0], (list, tuple)):
        emitter.segment_colors = [tuple(c) for c in colors[:3]]
    alphas = props.get('Alpha')
    if isinstance(alphas, (list, tuple)) and alphas:
        emitter.segment_alphas = tuple(int(round(v)) for v in alphas[:3])
    scaling = props.get('ParticleScaling')
    if isinstance(scaling, (list, tuple)) and scaling:
        emitter.segment_scaling = tuple(scaling[:3])
    emitter.texture_id = int(_scalar(props.get('TextureID'), -1))
    emitter.squirt = 1 if props.get('Squirt') else 0
    emitter.priority_plane = int(_scalar(props.get('PriorityPlane'), 0))
    emitter.replaceable_id = int(_scalar(props.get('ReplaceableId'), 0))
    model.nodes.append(emitter)
    model.particle_emitters_2.append(emitter)


def _parse_ribbon_emitter(t, model, name):
    emitter, props = _node_owner(t, model, classes.WarCraft3RibbonEmitter, name)
    for attr, key in (('height_above', 'HeightAbove'), ('height_below', 'HeightBelow'),
                      ('alpha', 'Alpha'), ('life_span', 'LifeSpan'), ('gravity', 'Gravity')):
        setattr(emitter, attr, float(_scalar(props.get(key), getattr(emitter, attr))))
    color = props.get('Color')
    if isinstance(color, classes.WarCraft3GeosetTransformation):
        color = color.values[0] if color.values else None
    if isinstance(color, tuple) and len(color) == 3:
        emitter.color = color
    emitter.texture_slot = int(_scalar(props.get('TextureSlot'), 0))
    emitter.emission_rate = int(_scalar(props.get('EmissionRate'), 0))
    emitter.rows = int(_scalar(props.get('Rows'), 0))
    emitter.columns = int(_scalar(props.get('Columns'), 0))
    emitter.material_id = int(_scalar(props.get('MaterialID'), 0))
    model.nodes.append(emitter)
    model.ribbon_emitters.append(emitter)


def _parse_light(t, model, name):
    light, props = _node_owner(t, model, classes.WarCraft3Light, name)
    for keyword, kind in LIGHT_TYPES.items():
        if props.get(keyword):
            light.light_type = kind
    track = classes.WarCraft3GeosetTransformation
    pairs = (('attenuation_start_track', 'AttenuationStart'), ('attenuation_end_track', 'AttenuationEnd'),
             ('color_track', 'Color'), ('intensity_track', 'Intensity'),
             ('ambient_color_track', 'AmbColor'), ('ambient_intensity_track', 'AmbIntensity'),
             ('visibility_track', 'Visibility'))
    for attr, key in pairs:
        if isinstance(props.get(key), track):
            setattr(light, attr, props[key])
    light.attenuation = (float(_scalar(props.get('AttenuationStart'), light.attenuation[0])),
                         float(_scalar(props.get('AttenuationEnd'), light.attenuation[1])))
    color = _scalar(props.get('Color'), light.color)
    if isinstance(color, tuple) and len(color) == 3:
        light.color = color
    ambient = _scalar(props.get('AmbColor'), light.ambient_color)
    if isinstance(ambient, tuple) and len(ambient) == 3:
        light.ambient_color = ambient
    light.intensity = float(_scalar(props.get('Intensity'), light.intensity))
    light.ambient_intensity = float(_scalar(props.get('AmbIntensity'), light.ambient_intensity))
    model.nodes.append(light)
    model.lights.append(light)


def _parse_camera(t, model, name):
    camera = classes.WarCraft3Camera()
    camera.name = name
    _, props = _props(t)
    position = props.get('Position')
    camera.position = tuple(position) if isinstance(position, tuple) else camera.position
    target = props.get('Target') or {}
    target_position = target.get('Position')
    camera.target_position = tuple(target_position) if isinstance(target_position, tuple) else camera.target_position
    camera.field_of_view = float(_scalar(props.get('FieldOfView'), 0.0))
    camera.near_clipping_plane = float(_scalar(props.get('NearClip'), 0.0))
    camera.far_clipping_plane = float(_scalar(props.get('FarClip'), 0.0))
    track = classes.WarCraft3GeosetTransformation
    if isinstance(props.get('Translation'), track):
        camera.translations = props['Translation']
    if isinstance(target.get('Translation'), track):
        camera.target_translations = target['Translation']
    if isinstance(props.get('Rotation'), track):
        camera.roll_track = props['Rotation']
    model.cameras.append(camera)


def parse_mdl(data):
    """Parse WarCraft 3 text .mdl data into a WarCraft3Model."""
    text = data.decode('utf-8', 'replace') if isinstance(data, (bytes, bytearray)) else data
    t = _Tokens(text)
    model = classes.WarCraft3Model()
    model.version = 800
    node_blocks = {'Bone': _parse_bone, 'Helper': _parse_helper, 'Attachment': _parse_attachment,
                   'EventObject': _parse_event, 'CollisionShape': _parse_collision_shape,
                   'ParticleEmitter': _parse_particle_emitter, 'ParticleEmitter2': _parse_particle_emitter_2,
                   'RibbonEmitter': _parse_ribbon_emitter, 'Light': _parse_light, 'Camera': _parse_camera}
    while not t.at_end():
        kind, value = t.peek()
        if kind != 'kw':
            t.take()
            continue
        keyword = _kw(t)
        if keyword == 'Version':
            _, props = _props(t)
            model.version = int(_scalar(props.get('FormatVersion'), 800))
        elif keyword == 'Model':
            model.name = '' if t.is_sym('{') else _str(t)
            _open(t)
            _skip_block(t)
        elif keyword in node_blocks:
            name = _str(t) if not t.is_sym('{') else ''
            _open(t)
            node_blocks[keyword](t, model, name)
        elif keyword == 'Geoset':
            _open(t)
            _parse_geoset(t, model)
        elif keyword == 'GeosetAnim':
            _open(t)
            _parse_geoset_anim(t, model)
        elif keyword == 'Material':
            _open(t)
            _parse_material(t, model)
        elif keyword == 'Bitmap':
            _open(t)
            _parse_texture(t, model)
        elif keyword == 'Anim':
            name = _str(t)
            _open(t)
            sequence = classes.WarCraft3Sequence()
            sequence.name = name
            _, props = _props(t)
            interval = props.get('Interval')
            if isinstance(interval, tuple) and len(interval) == 2:
                sequence.interval_start, sequence.interval_end = int(interval[0]), int(interval[1])
            else:
                sequence.interval_start, sequence.interval_end = 0, 0
            sequence.flags = 1 if props.get('NonLooping') else 0
            model.sequences.append(sequence)
        elif keyword == 'TVertexAnim':
            _open(t)
            _, props = _props(t)
            anim = classes.WarCraft3TextureAnimation()
            track = classes.WarCraft3GeosetTransformation
            for attr, key in (('translations', 'Translation'), ('rotations', 'Rotation'),
                              ('scalings', 'Scaling')):
                if isinstance(props.get(key), track):
                    setattr(anim, attr, props[key])
            model.texture_animations.append(anim)
        elif keyword == 'Duration':
            model.global_sequences.append(int(_scalar(_value(t), 0)))
        elif keyword == 'PivotPoints':
            points = _value(t)
            model.pivot_points = [tuple(point) for point in points] if isinstance(points, list) else []
        else:
            # Container ("Sequences 2 {", "Bitmap {") or a plain top-level property.
            # Containers are entered, not skipped, so their inner keywords dispatch here too.
            if t.peek()[0] == 'num' and t.peek(1) == ('sym', '{'):
                t.pos += 2
            elif t.is_sym('{'):
                t.pos += 1
            else:
                _value(t)
    if model.name is None:
        model.name = ''
    return model


def _parse_material(t, model):
    material = classes.WarCraft3Material()
    while not t.at_end() and not _close(t):
        kind, value = t.peek()
        if kind == 'kw' and value == 'Layer':
            t.take()
            _open(t)
            material.layers.append(_parse_layer(t))
        elif kind == 'kw' and value == 'PriorityPlane':
            t.take()
            material.priority_plane = int(_scalar(_value(t), 0))
        elif kind == 'kw' and value in MATERIAL_FLAGS:
            t.take()
            material.flags |= MATERIAL_FLAGS[value]
        elif kind == 'kw':
            t.take()
            _value(t)
        else:
            t.take()
    model.materials.append(material)


def _parse_texture(t, model):
    texture = classes.WarCraft3Texture()
    _, props = _props(t)
    image = props.get('Image')
    texture.image_file_name = image if isinstance(image, str) else ''
    texture.replaceable_id = int(_scalar(props.get('ReplaceableId'), 0))
    for keyword, bit in TEXTURE_FLAGS.items():
        if props.get(keyword):
            texture.flags |= bit
    model.textures.append(texture)
