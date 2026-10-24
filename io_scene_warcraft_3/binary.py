import struct


class Reader:
    def __init__(self, data):
        self.__data = data
        self.offset = 0

    def getf(self, format):
        size = struct.calcsize(format)
        self.offset += size
        return struct.unpack_from(format, self.__data, self.offset - size)

    def gets(self, size):
        self.offset += size
        raw = struct.unpack_from('<{}s'.format(size), self.__data, self.offset - size)[0].split(b'\x00')[0]
        try:
            return raw.decode(encoding='utf-8')
        except Exception:
            try:
                return raw.decode(encoding='mbcs')
            except Exception:
                return raw.decode(encoding='latin1', errors='ignore')

    def getid(self, requiredChunksId=None, debug=False):
        self.offset += 4
        raw = struct.unpack_from('<4s', self.__data, self.offset - 4)[0]
        try:
            chunkId = raw.decode(encoding='latin1')
        except Exception:
            chunkId = raw.decode(encoding='utf-8', errors='ignore')
        if requiredChunksId is not None:
            if type(requiredChunksId) == str:
                requiredChunksId = [requiredChunksId, ]
            if chunkId not in requiredChunksId:
                if not debug:
                    raise Exception('chunk id "{0}" not in "{1}"'.format(chunkId, requiredChunksId))
        return chunkId

    def skip(self, count):
        self.offset += count
