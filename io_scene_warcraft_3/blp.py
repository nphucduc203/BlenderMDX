"""
Warcraft III / Blizzard BLP Texture Decoder for Blender
Supports:
- BLP1 JPEG (with 4-channel CMYK/RGBA inversion: R=255-Y, G=255-M, B=255-C, A=255-K; 3-channel RGB: BGR; Grayscale)
- BLP1 Paletted (256-color palette BGRA->RGBA, alpha_bits=0, 1, 4, 8 with separate bitstream alpha unpacking)
- BLP2 (DirectX DXT1, DXT3, DXT5, and raw uncompressed BGRA)
- Fallback loading for other formats (PNG, TGA, DDS, JPG)
"""

import io
import os
import struct
from PIL import Image, ImageOps
from PIL.JpegImagePlugin import JpegImageFile

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def decode_blp(file_or_path):
    """
    Decodes a BLP file (path, file-like object, or bytes) into a PIL.Image (RGBA).
    """
    if isinstance(file_or_path, str):
        with open(file_or_path, 'rb') as f:
            data = f.read()
    elif hasattr(file_or_path, 'read'):
        data = file_or_path.read()
    else:
        data = bytes(file_or_path)

    if len(data) < 20:
        raise ValueError("Data too short to be a valid BLP image.")

    magic = data[:4]

    if magic == b'BLP1':
        content, alpha_bits, width, height, type_, has_mips = struct.unpack('<6I', data[4:28])
        offsets = struct.unpack('<16I', data[28:92])
        lengths = struct.unpack('<16I', data[92:156])

        if content == 0:  # JPEG compression
            jpeg_header_size = struct.unpack('<I', data[156:160])[0]
            jpeg_header = data[160:160 + jpeg_header_size]
            m0_off = offsets[0]
            m0_len = lengths[0]
            jpeg_stream = jpeg_header + data[m0_off:m0_off + m0_len]

            jpg = JpegImageFile(io.BytesIO(jpeg_stream))
            if jpg.mode == 'CMYK':
                args = jpg.tile[0].args
                jpg.tile = [jpg.tile[0]._replace(args=(args[0], "CMYK"))]
                c, m, y, k = jpg.split()
                # In Warcraft III BLP1 JPEG:
                # Channel 0 (C) is 255 - Blue
                # Channel 1 (M) is 255 - Green
                # Channel 2 (Y) is 255 - Red
                # Channel 3 (K) is 255 - Alpha
                r = ImageOps.invert(y)
                g = ImageOps.invert(m)
                b = ImageOps.invert(c)
                if alpha_bits > 0:
                    a = ImageOps.invert(k)
                else:
                    a = Image.new('L', (width, height), 255)
                return Image.merge("RGBA", (r, g, b, a))
            elif jpg.mode == 'RGB':
                # 3 channels in BGR order
                b, g, r = jpg.split()
                a = Image.new('L', (width, height), 255)
                return Image.merge("RGBA", (r, g, b, a))
            else:
                return jpg.convert("RGBA")

        elif content == 1:  # Paletted (indexed) compression
            pal_raw = data[156:156 + 1024]
            m0_off = offsets[0]
            m0_len = lengths[0]
            num_pixels = width * height
            alpha_off = m0_off + num_pixels

            if HAS_NUMPY:
                # Fast NumPy vectorization
                pal_bgra = np.frombuffer(pal_raw, dtype=np.uint8).reshape((256, 4))
                pal_rgba = np.empty((256, 4), dtype=np.uint8)
                pal_rgba[:, 0] = pal_bgra[:, 2]  # R
                pal_rgba[:, 1] = pal_bgra[:, 1]  # G
                pal_rgba[:, 2] = pal_bgra[:, 0]  # B
                pal_rgba[:, 3] = 255             # default Alpha

                indices = np.frombuffer(data[m0_off:m0_off + num_pixels], dtype=np.uint8)
                out_pixels = pal_rgba[indices].copy()

                if alpha_bits == 1:
                    alpha_bytes = np.frombuffer(data[alpha_off:alpha_off + (num_pixels + 7) // 8], dtype=np.uint8)
                    bits = np.unpackbits(alpha_bytes, bitorder='little')[:num_pixels]
                    out_pixels[:, 3] = bits * 255
                elif alpha_bits == 4:
                    alpha_bytes = np.frombuffer(data[alpha_off:alpha_off + (num_pixels + 1) // 2], dtype=np.uint8)
                    low = alpha_bytes & 0x0F
                    high = (alpha_bytes >> 4) & 0x0F
                    nibbles = np.empty(num_pixels, dtype=np.uint8)
                    half = num_pixels // 2
                    nibbles[0::2] = low[:half + (num_pixels % 2)]
                    nibbles[1::2] = high[:half]
                    out_pixels[:, 3] = nibbles * 17
                elif alpha_bits == 8:
                    out_pixels[:, 3] = np.frombuffer(data[alpha_off:alpha_off + num_pixels], dtype=np.uint8)
                else:
                    out_pixels[:, 3] = 255

                return Image.fromarray(out_pixels.reshape((height, width, 4)), "RGBA")

            else:
                # Pure Python fallback
                palette = []
                for i in range(256):
                    b, g, r, _ = pal_raw[i * 4:(i + 1) * 4]
                    palette.append((r, g, b))

                indices = data[m0_off:m0_off + num_pixels]
                alpha_data = data[alpha_off:]
                rgba = bytearray(num_pixels * 4)

                for i in range(num_pixels):
                    idx = indices[i]
                    r, g, b = palette[idx]
                    if alpha_bits == 0:
                        a = 255
                    elif alpha_bits == 1:
                        byte_val = alpha_data[i // 8]
                        bit = (byte_val >> (i % 8)) & 1
                        a = 255 if bit else 0
                    elif alpha_bits == 4:
                        byte_val = alpha_data[i // 2]
                        nibble = (byte_val >> ((i % 2) * 4)) & 0x0F
                        a = nibble * 17
                    elif alpha_bits == 8:
                        a = alpha_data[i]
                    else:
                        a = 255

                    rgba[i * 4 + 0] = r
                    rgba[i * 4 + 1] = g
                    rgba[i * 4 + 2] = b
                    rgba[i * 4 + 3] = a

                return Image.frombytes("RGBA", (width, height), bytes(rgba))

        else:
            raise ValueError(f"Unsupported BLP1 content type: {content}")

    elif magic == b'BLP2':
        # BLP2 (World of Warcraft / Reforged) - Pillow's BLP2 decoder handles DXT1/3/5 correctly
        im = Image.open(io.BytesIO(data))
        return im.convert("RGBA")

    else:
        # Fallback to standard Pillow format handler
        im = Image.open(io.BytesIO(data))
        return im.convert("RGBA")


def blp_to_png(blp_filepath, output_png_path):
    """
    Decodes blp_filepath and saves it to output_png_path.
    Creates parent directories if necessary.
    """
    img = decode_blp(blp_filepath)
    os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)
    img.save(output_png_path, 'PNG')
    return output_png_path
