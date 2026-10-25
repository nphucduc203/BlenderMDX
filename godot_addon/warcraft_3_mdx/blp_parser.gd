@tool
class_name BlpParser
extends RefCounted

## Warcraft 3 BLP1 / BLP2 Texture Decoder for Godot 4
## Decodes BLP files directly into Godot Image objects.

static func load_from_file(path: String) -> Image:
	var f = FileAccess.open(path, FileAccess.READ)
	if not f:
		return null
	var buffer = f.get_buffer(f.get_length())
	return parse_buffer(buffer)


static func parse_buffer(data: PackedByteArray) -> Image:
	if data.size() < 20:
		return null

	var magic = data.slice(0, 4).get_string_from_ascii()

	if magic == "BLP1":
		return _parse_blp1(data)
	elif magic == "BLP2":
		return _parse_blp2(data)

	return null


static func _parse_blp1(data: PackedByteArray) -> Image:
	var spb = StreamPeerBuffer.new()
	spb.data_array = data
	spb.seek(4)

	var content = spb.get_u32()     # 0 = JPEG, 1 = Paletted
	var alpha_bits = spb.get_u32()  # 0, 1, 4, 8
	var width = spb.get_u32()
	var height = spb.get_u32()
	var _type = spb.get_u32()
	var _has_mips = spb.get_u32()

	var mip_offsets: Array[int] = []
	for i in range(16):
		mip_offsets.append(spb.get_u32())

	var mip_lengths: Array[int] = []
	for i in range(16):
		mip_lengths.append(spb.get_u32())

	if width == 0 or height == 0:
		return null

	var m0_off = mip_offsets[0]
	var m0_len = mip_lengths[0]

	if content == 1:
		# Paletted Compression (256 RGBA colors)
		var palette_offset = 156
		if data.size() < palette_offset + 1024:
			return null

		var pal_raw = data.slice(palette_offset, palette_offset + 1024)
		var num_pixels = width * height
		var indices_offset = m0_off

		if data.size() < indices_offset + num_pixels:
			return null

		var alpha_offset = indices_offset + num_pixels
		var out = PackedByteArray()
		out.resize(num_pixels * 4)

		for i in range(num_pixels):
			var idx = data[indices_offset + i]
			var pal_pos = idx * 4
			# BLP1 palette is BGRA: B=0, G=1, R=2, A=3
			var b = pal_raw[pal_pos + 0]
			var g = pal_raw[pal_pos + 1]
			var r = pal_raw[pal_pos + 2]
			var a = 255

			if alpha_bits == 8:
				if alpha_offset + i < data.size():
					a = data[alpha_offset + i]
			elif alpha_bits == 1:
				var byte_idx = alpha_offset + (i >> 3)
				var bit_idx = i & 7
				if byte_idx < data.size():
					a = 255 if ((data[byte_idx] >> bit_idx) & 1) else 0
			elif alpha_bits == 4:
				var byte_idx = alpha_offset + (i >> 1)
				if byte_idx < data.size():
					var nibble = (data[byte_idx] >> (4 if (i & 1) else 0)) & 0x0F
					a = nibble * 17
			elif alpha_bits == 0:
				a = pal_raw[pal_pos + 3]

			var dst = i * 4
			out[dst + 0] = r
			out[dst + 1] = g
			out[dst + 2] = b
			out[dst + 3] = a

		var img = Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, out)
		return img

	elif content == 0:
		# JPEG Compression
		spb.seek(156)
		var jpeg_header_size = spb.get_u32()
		var jpeg_header = data.slice(160, 160 + jpeg_header_size)
		var jpeg_stream = PackedByteArray()
		jpeg_stream.append_array(jpeg_header)
		jpeg_stream.append_array(data.slice(m0_off, m0_off + m0_len))

		var raw_img = Image.new()
		var err = raw_img.load_jpg_from_buffer(jpeg_stream)
		if err != OK:
			return null

		# Handle Warcraft 3 BLP1 JPEG inverted CMYK / BGR channels
		raw_img.convert(Image.FORMAT_RGBA8)
		var raw_data = raw_img.get_data()
		var px_count = width * height
		if raw_data.size() >= px_count * 4:
			for i in range(px_count):
				var pos = i * 4
				# Warcraft 3 BLP1 JPEG CMYK inversion:
				# C -> B (invert), M -> G (invert), Y -> R (invert), K -> A (invert)
				var c = raw_data[pos + 0]
				var m = raw_data[pos + 1]
				var y = raw_data[pos + 2]
				var k = raw_data[pos + 3]
				raw_data[pos + 0] = 255 - y
				raw_data[pos + 1] = 255 - m
				raw_data[pos + 2] = 255 - c
				raw_data[pos + 3] = (255 - k) if alpha_bits > 0 else 255
			return Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, raw_data)
		return raw_img

	return null


static func _parse_blp2(data: PackedByteArray) -> Image:
	var spb = StreamPeerBuffer.new()
	spb.data_array = data
	spb.seek(4)

	var _type = spb.get_u32()
	var encoding = spb.get_u32()    # 1 = uncompressed BGRA, 2 = DXT
	var alpha_bits = spb.get_u32()
	var alpha_type = spb.get_u32()  # 0 = DXT1, 1 = DXT3, 7 = DXT5
	var _has_mips = spb.get_u32()
	var width = spb.get_u32()
	var height = spb.get_u32()

	var mip_offsets: Array[int] = []
	for i in range(16):
		mip_offsets.append(spb.get_u32())

	var mip_lengths: Array[int] = []
	for i in range(16):
		mip_lengths.append(spb.get_u32())

	if width == 0 or height == 0:
		return null

	var m0_off = mip_offsets[0]
	var m0_len = mip_lengths[0]
	var m0_data = data.slice(m0_off, m0_off + m0_len)

	if encoding == 2:
		# DXT Compression
		var format = Image.FORMAT_DXT1
		if alpha_type == 1:
			format = Image.FORMAT_DXT3
		elif alpha_type == 7 or alpha_bits > 1:
			format = Image.FORMAT_DXT5
		var img = Image.create_from_data(width, height, false, format, m0_data)
		if img:
			img.decompress()
		return img

	elif encoding == 1:
		# Uncompressed BGRA -> RGBA
		var out = PackedByteArray()
		out.resize(width * height * 4)
		for i in range(width * height):
			var src = i * 4
			out[src + 0] = m0_data[src + 2] # R
			out[src + 1] = m0_data[src + 1] # G
			out[src + 2] = m0_data[src + 0] # B
			out[src + 3] = m0_data[src + 3] # A
		return Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, out)

	return null
