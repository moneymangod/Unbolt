"""Build a tiny synthetic .fig (kiwi schema + message) to exercise the parser and renderer.

This only proves the code is self-consistent; it is not a substitute for a file saved by Figma itself.
"""
import io
import struct
import sys
import zipfile
import zlib

PRIMS = ["bool", "byte", "int", "uint", "float", "string", "int64", "uint64"]
E, S, M = 0, 1, 2
F = lambda name, typ, id_=0, arr=False: (name, typ, id_, arr)
DEFS = {
    "NodeType": (E, [F("DOCUMENT", None, 0), F("CANVAS", None, 1), F("FRAME", None, 2), F("RECTANGLE", None, 3), F("ELLIPSE", None, 4), F("TEXT", None, 5)]),
    "PaintType": (E, [F("SOLID", None, 0)]),
    "GUID": (S, [F("sessionID", "uint"), F("localID", "uint")]),
    "Color": (S, [F("r", "float"), F("g", "float"), F("b", "float"), F("a", "float")]),
    "Vector": (S, [F("x", "float"), F("y", "float")]),
    "Matrix": (S, [F(k, "float") for k in ("m00", "m01", "m02", "m10", "m11", "m12")]),
    "ParentIndex": (M, [F("guid", "GUID", 1), F("position", "string", 2)]),
    "Paint": (M, [F("type", "PaintType", 1), F("color", "Color", 2), F("opacity", "float", 3), F("visible", "bool", 4)]),
    "TextData": (M, [F("characters", "string", 1)]),
    "NodeChange": (M, [F("guid", "GUID", 1), F("parentIndex", "ParentIndex", 2), F("type", "NodeType", 3), F("name", "string", 4),
                       F("size", "Vector", 5), F("transform", "Matrix", 6), F("fillPaints", "Paint", 7, True),
                       F("cornerRadius", "float", 8), F("textData", "TextData", 9), F("fontSize", "float", 10)]),
    "Message": (M, [F("nodeChanges", "NodeChange", 1, True)]),
}
ORDER = list(DEFS)


def varuint(n):
    out = b""
    while True:
        b = n & 127
        n >>= 7
        out += bytes([b | (128 if n else 0)])
        if not n:
            return out


def varint(n):
    return varuint((~n << 1) | 1 if n < 0 else n << 1)


def varfloat(x):
    if x == 0:
        return b"\0"
    bits = struct.unpack("<I", struct.pack("<f", x))[0]
    bits = ((bits >> 23) | (bits << 9)) & 0xFFFFFFFF
    return struct.pack("<I", bits)


def schema_bytes():
    out = varuint(len(DEFS))
    for name, (kind, fields) in DEFS.items():
        out += name.encode() + b"\0" + bytes([kind]) + varuint(len(fields))
        for fname, typ, id_, arr in fields:
            t = 0 if typ is None else (varint(~PRIMS.index(typ)) if typ in PRIMS else varint(ORDER.index(typ)))
            out += fname.encode() + b"\0" + (varint(0) if typ is None else t) + bytes([1 if arr else 0]) + varuint(id_)
    return out


def enc(typ, v):
    if typ == "bool":
        return bytes([v])
    if typ == "uint":
        return varuint(v)
    if typ == "float":
        return varfloat(v)
    if typ == "string":
        return v.encode() + b"\0"
    kind, fields = DEFS[typ]
    if kind == E:
        return varuint(next(f[2] for f in fields if f[0] == v))
    if kind == S:
        return b"".join(enc(f[1], v[f[0]]) for f in fields)
    out = b""
    for fname, ftyp, id_, arr in fields:
        if fname in v:
            val = v[fname]
            out += varuint(id_)
            out += varuint(len(val)) + b"".join(enc(ftyp, x) for x in val) if arr else enc(ftyp, val)
    return out + varuint(0)


def node(local, parent, pos, typ, name, w, h, x=0, y=0, fill=None, **extra):
    n = {"guid": {"sessionID": 1, "localID": local}, "type": typ, "name": name, "size": {"x": w, "y": h},
         "transform": {"m00": 1, "m01": 0, "m02": x, "m10": 0, "m11": 1, "m12": y}}
    if parent:
        n["parentIndex"] = {"guid": {"sessionID": 1, "localID": parent}, "position": pos}
    if fill:
        n["fillPaints"] = [{"type": "SOLID", "color": dict(zip("rgba", fill)), "opacity": 1.0, "visible": True}]
    return n | extra


nodes = [
    node(1, None, "", "DOCUMENT", "Doc", 0, 0),
    node(2, 1, "a", "CANVAS", "Page 1", 0, 0),
    node(3, 2, "a", "FRAME", "Card", 320, 200, fill=(0.95, 0.95, 1, 1)),
    node(4, 3, "a", "RECTANGLE", "Box", 120, 80, 20, 20, fill=(0.2, 0.4, 0.9, 1), cornerRadius=12.0),
    node(5, 3, "b", "ELLIPSE", "Dot", 60, 60, 220, 20, fill=(0.9, 0.3, 0.3, 1)),
    node(6, 3, "c", "TEXT", "Label", 200, 30, 20, 130, fill=(0, 0, 0, 1), textData={"characters": "Hello from a .fig"}, fontSize=18.0),
    node(7, 2, "b", "FRAME", "Second", 200, 100, fill=(1, 1, 0.8, 1)),
]
fig = b"fig-kiwi" + struct.pack("<I", 15)
for chunk in (schema_bytes(), enc("Message", {"nodeChanges": nodes})):
    c = zlib.compressobj(wbits=-15)
    data = c.compress(chunk) + c.flush()
    fig += struct.pack("<I", len(data)) + data

if sys.argv[1].endswith(".fig"):
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("canvas.fig", fig)
        z.writestr("meta.json", "{}")
    open(sys.argv[1], "wb").write(zbuf.getvalue())
