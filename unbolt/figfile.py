"""Read Figma .fig files and render their top-level frames to images (best effort)."""
import io
import math
import re
import struct
import zipfile
import zlib

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

_PRIMS = ["bool", "byte", "int", "uint", "float", "string", "int64", "uint64"]
_KINDS = ["ENUM", "STRUCT", "MESSAGE"]


class _Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def byte(self):
        b = self.d[self.i]
        self.i += 1
        return b

    def varuint(self):
        v = shift = 0
        while True:
            b = self.byte()
            v |= (b & 127) << shift
            shift += 7
            if not b & 128:
                return v

    def varint(self):
        v = self.varuint()
        return ~(v >> 1) if v & 1 else v >> 1

    def varfloat(self):
        if self.d[self.i] == 0:
            self.i += 1
            return 0.0
        bits = struct.unpack_from("<I", self.d, self.i)[0]
        self.i += 4
        bits = ((bits << 23) | (bits >> 9)) & 0xFFFFFFFF
        return struct.unpack("<f", struct.pack("<I", bits))[0]

    def string(self):
        end = self.d.index(0, self.i)
        s = self.d[self.i:end].decode("utf-8", "replace")
        self.i = end + 1
        return s

    def bytes(self):
        n = self.varuint()
        b = self.d[self.i:self.i + n]
        self.i += n
        return bytes(b)


def _decode_schema(data):
    r = _Reader(data)
    defs = []
    for _ in range(r.varuint()):
        name, kind = r.string(), _KINDS[r.byte()]
        fields = []
        for _ in range(r.varuint()):
            fname, ftype = r.string(), r.varint()
            is_array = bool(r.byte() & 1)
            fields.append({"name": fname, "type": ftype, "array": is_array, "id": r.varuint()})
        defs.append({"name": name, "kind": kind, "fields": fields})
    for d in defs:
        for f in d["fields"]:
            t = f["type"]
            f["type"] = None if d["kind"] == "ENUM" else (_PRIMS[~t] if t < 0 else defs[t]["name"])
    return {d["name"]: d for d in defs}


def _read_value(r, schema, t):
    if t == "bool":
        return bool(r.byte())
    if t == "byte":
        return r.byte()
    if t in ("int", "int64"):
        return r.varint()
    if t in ("uint", "uint64"):
        return r.varuint()
    if t == "float":
        return r.varfloat()
    if t == "string":
        return r.string()
    d = schema[t]
    if d["kind"] == "ENUM":
        v = r.varuint()
        return next((f["name"] for f in d["fields"] if f["id"] == v), v)
    if d["kind"] == "STRUCT":
        return {f["name"]: _read_field(r, schema, f) for f in d["fields"]}
    out = {}
    while True:
        fid = r.varuint()
        if fid == 0:
            return out
        f = next(f for f in d["fields"] if f["id"] == fid)
        out[f["name"]] = _read_field(r, schema, f)


def _read_field(r, schema, f):
    if f["array"]:
        if f["type"] == "byte":
            return r.bytes()
        return [_read_value(r, schema, f["type"]) for _ in range(r.varuint())]
    return _read_value(r, schema, f["type"])


def _inflate(chunk):
    if chunk[:4] == b"\x28\xb5\x2f\xfd":
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(chunk)
    return zlib.decompress(chunk, -15)


def load_fig(path):
    """Return (message, images, thumbnail). `images` maps hex hash -> bytes."""
    raw = open(path, "rb").read()
    images, thumb = {}, None
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
        if "thumbnail.png" in names:
            thumb = z.read("thumbnail.png")
        images = {n.split("/", 1)[1]: z.read(n) for n in names if n.startswith("images/") and not n.endswith("/")}
        raw = z.read("canvas.fig")
    if raw[:8] != b"fig-kiwi":
        raise ValueError("Not a Figma file (missing fig-kiwi header)")
    chunks, off = [], 12
    while off + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, off)[0]
        chunks.append(raw[off + 4:off + 4 + n])
        off += 4 + n
    schema = _decode_schema(_inflate(chunks[0]))
    message = _read_value(_Reader(_inflate(chunks[1])), schema, "Message")
    return message, images, thumb


# ---------------------------------------------------------------- rendering

def _guid(g):
    return (g["sessionID"], g["localID"]) if g else None


class _Doc:
    def __init__(self, message, images):
        self.blobs = message.get("blobs", [])
        self.images = images
        self.nodes = {}
        self.children = {}
        for n in message.get("nodeChanges", []):
            self.nodes[_guid(n["guid"])] = n
        for n in self.nodes.values():
            pi = n.get("parentIndex")
            if pi:
                self.children.setdefault(_guid(pi["guid"]), []).append(n)
        for kids in self.children.values():
            kids.sort(key=lambda k: k["parentIndex"].get("position", ""))

    def kids(self, node):
        k = self.children.get(_guid(node["guid"]), [])
        sym = (node.get("symbolData") or {}).get("symbolID")
        if not k and sym and _guid(sym) in self.nodes:
            k = self.children.get(_guid(sym), [])
        return k

    def frames(self):
        out = []
        for c in self.nodes.values():
            if c.get("type") == "CANVAS" and "Internal" not in c.get("name", ""):
                out += [(c.get("name", ""), n) for n in self.children.get(_guid(c["guid"]), [])
                        if n.get("visible", True) and n.get("size")]
        return out


def _mat(t):
    if not t:
        return np.eye(3)
    return np.array([[t.get("m00", 1), t.get("m01", 0), t.get("m02", 0)],
                     [t.get("m10", 0), t.get("m11", 1), t.get("m12", 0)], [0, 0, 1]], float)


def _apply(m, pts):
    p = np.c_[np.asarray(pts, float), np.ones(len(pts))] @ m.T
    return [tuple(x) for x in p[:, :2]]


def _rect_poly(w, h, radii):
    if not any(radii):
        return [(0, 0), (w, 0), (w, h), (0, h)]
    pts = []
    for (cx, cy, a0), r in zip(((w, 0, -90), (w, h, 0), (0, h, 90), (0, 0, 180)), (radii[1], radii[2], radii[3], radii[0])):
        r = min(r, w / 2, h / 2)
        ox = cx - r if cx else cx + r
        oy = cy - r if cy else cy + r
        pts += [(ox + r * math.cos(math.radians(a0 + k * 90 / 8)), oy + r * math.sin(math.radians(a0 + k * 90 / 8)))
                for k in range(9)]
    return pts


def _path_polys(blob):
    """Decode a Figma path blob (moveTo/lineTo/quad/cubic/close) to flattened polylines."""
    b, i, polys, cur, pos = blob, 0, [], [], (0, 0)

    def f():
        nonlocal i
        v = struct.unpack_from("<f", b, i)[0]
        i += 4
        return v

    while i < len(b):
        c = b[i]
        i += 1
        if c == 1:
            if len(cur) > 1:
                polys.append(cur)
            pos = (f(), f())
            cur = [pos]
        elif c == 2:
            pos = (f(), f())
            cur.append(pos)
        elif c == 3:
            p1, p2, p3 = (f(), f()), (f(), f()), (f(), f())
            cur += [tuple((1 - t) ** 3 * np.array(pos) + 3 * (1 - t) ** 2 * t * np.array(p1)
                          + 3 * (1 - t) * t * t * np.array(p2) + t ** 3 * np.array(p3)) for t in np.linspace(0, 1, 13)[1:]]
            pos = p3
        elif c == 4:
            p1, p2 = (f(), f()), (f(), f())
            cur += [tuple((1 - t) ** 2 * np.array(pos) + 2 * (1 - t) * t * np.array(p1) + t * t * np.array(p2))
                    for t in np.linspace(0, 1, 9)[1:]]
            pos = p2
        elif c == 0:
            if cur:
                polys.append(cur)
            cur = []
        else:
            break
    if len(cur) > 1:
        polys.append(cur)
    return polys


def _font(size, style=""):
    for name in (("arialbd.ttf" if "Bold" in style else "arial.ttf"), "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, max(int(size), 1))
        except OSError:
            continue
    return ImageFont.load_default()


class _Renderer:
    def __init__(self, doc, w, h, scale):
        self.doc, self.s, self.skipped = doc, scale, 0
        self.img = Image.new("RGBA", (int(w * scale), int(h * scale)), (255, 255, 255, 0))
        self.size = self.img.size

    def mask(self, polys):
        m = Image.new("L", self.size, 0)
        d = ImageDraw.Draw(m)
        for p in polys:
            if len(p) > 2:
                d.polygon([(x * self.s, y * self.s) for x, y in p], fill=255)
        return m

    def paint(self, fill, mask, clip, node, m):
        if not fill.get("visible", True):
            return
        op = fill.get("opacity", 1.0) * node.get("opacity", 1.0)
        mask = ImageChops.multiply(mask, clip)
        bbox = mask.getbbox()
        if not bbox:
            return
        kind = fill.get("type")
        if kind == "SOLID":
            c = fill["color"]
            layer = Image.new("RGBA", self.size, (int(c["r"] * 255), int(c["g"] * 255), int(c["b"] * 255), 255))
            op *= c.get("a", 1.0)
        elif kind and kind.startswith("GRADIENT"):
            layer = self.gradient(fill, bbox)
        elif kind == "IMAGE":
            layer = self.image_fill(fill, bbox)
        else:
            return
        if layer is None:
            return
        alpha = ImageChops.multiply(mask, layer.getchannel("A")).point(lambda v: int(v * op))
        self.img.alpha_composite(Image.merge("RGBA", (*layer.split()[:3], alpha)))

    def gradient(self, fill, bbox):
        stops = fill.get("stops") or []
        if not stops:
            return None
        x0, y0, x1, y1 = bbox
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        yy, xx = np.mgrid[0:h, 0:w]
        t = (xx / w) if fill["type"] != "GRADIENT_RADIAL" else np.hypot(xx / w - .5, yy / h - .5) * 2
        if fill["type"] == "GRADIENT_LINEAR":
            g = _mat(fill.get("transform"))
            try:
                gi = np.linalg.inv(g)
                px, py = xx / w, yy / h
                t = gi[0, 0] * px + gi[0, 1] * py + gi[0, 2]
            except np.linalg.LinAlgError:
                pass
        t = np.clip(t, 0, 1)
        pos = [s["position"] for s in stops]
        chans = [np.interp(t, pos, [s["color"][k] * 255 for s in stops]) for k in "rgba"]
        chans[3] = np.interp(t, pos, [s["color"]["a"] * 255 for s in stops])
        tile = np.stack(chans, -1).astype(np.uint8)
        layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
        layer.paste(Image.fromarray(tile, "RGBA"), (x0, y0))
        return layer

    def image_fill(self, fill, bbox):
        h = (fill.get("image") or {}).get("hash")
        data = self.doc.images.get(bytes(h).hex()) if h else None
        if not data:
            return None
        try:
            src = Image.open(io.BytesIO(data)).convert("RGBA")
        except OSError:
            return None
        x0, y0, x1, y1 = bbox
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        k = max(w / src.width, h / src.height)
        src = src.resize((max(int(src.width * k), 1), max(int(src.height * k), 1)))
        layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
        layer.paste(src, (x0 + (w - src.width) // 2, y0 + (h - src.height) // 2))
        return layer

    def stroke(self, node, polys, clip, m):
        weight = node.get("strokeWeight", 0) or 0
        paints = [p for p in node.get("strokePaints", []) if p.get("visible", True) and p.get("type") == "SOLID"]
        if not weight or not paints:
            return
        sm = Image.new("L", self.size, 0)
        d = ImageDraw.Draw(sm)
        for p in polys:
            pts = [(x * self.s, y * self.s) for x, y in p]
            d.line(pts + pts[:1], fill=255, width=max(int(weight * self.s * math.sqrt(abs(np.linalg.det(m[:2, :2])))), 1), joint="curve")
        for p in paints:
            self.paint(p, sm, clip, node, m)

    def draw(self, node, parent_m, clip):
        if not node.get("visible", True) or node.get("opacity", 1) == 0:
            return
        t = node.get("type")
        m = parent_m @ _mat(node.get("transform"))
        w, h = (node.get("size") or {}).get("x", 0), (node.get("size") or {}).get("y", 0)
        fills = [f for f in node.get("fillPaints", []) if f.get("visible", True)]
        polys = []
        if t in ("RECTANGLE", "ROUNDED_RECTANGLE", "FRAME", "SYMBOL", "INSTANCE", "SECTION"):
            r = node.get("cornerRadius", 0) or 0
            radii = [node.get(k, r) or 0 for k in ("rectangleTopLeftCornerRadius", "rectangleTopRightCornerRadius",
                                                     "rectangleBottomRightCornerRadius", "rectangleBottomLeftCornerRadius")]
            polys = [_apply(m, _rect_poly(w, h, radii))]
        elif t == "ELLIPSE":
            polys = [_apply(m, [(w / 2 + w / 2 * math.cos(a), h / 2 + h / 2 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 64)])]
        elif t in ("VECTOR", "LINE", "STAR", "REGULAR_POLYGON", "BOOLEAN_OPERATION"):
            for g in node.get("fillGeometry", []) or []:
                bi = g.get("commandsBlob")
                if bi is not None and bi < len(self.doc.blobs):
                    polys += [_apply(m, p) for p in _path_polys(self.doc.blobs[bi]["bytes"])]
            if not polys and t != "BOOLEAN_OPERATION":
                polys = [_apply(m, _rect_poly(w, h, [0] * 4))]
        elif t == "TEXT":
            self.text(node, m, clip)
            return
        if polys and t in ("FRAME", "SYMBOL", "INSTANCE", "SECTION", "RECTANGLE", "ROUNDED_RECTANGLE", "ELLIPSE", "VECTOR",
                           "LINE", "STAR", "REGULAR_POLYGON", "BOOLEAN_OPERATION"):
            mask = self.mask(polys)
            for f in fills:
                self.paint(f, mask, clip, node, m)
            if t != "LINE":
                self.stroke(node, polys, clip, m)
        child_clip = clip
        if t in ("FRAME", "SYMBOL", "INSTANCE") and not node.get("frameMaskDisabled", False) and polys:
            child_clip = ImageChops.multiply(clip, self.mask(polys[:1]))
        for kid in self.doc.kids(node):
            try:
                self.draw(kid, m, child_clip)
            except Exception:
                self.skipped += 1

    def text(self, node, m, clip):
        chars = (node.get("textData") or {}).get("characters", "")
        fills = [f for f in node.get("fillPaints", []) if f.get("visible", True) and f.get("type") == "SOLID"]
        if not chars or not fills:
            return
        c = fills[0]["color"]
        size = (node.get("fontSize") or 12) * self.s * math.sqrt(abs(np.linalg.det(m[:2, :2])))
        font = _font(size, (node.get("fontName") or {}).get("style", ""))
        w, h = (node.get("size") or {}).get("x", 0), (node.get("size") or {}).get("y", 0)
        lines, width = [], w * self.s * math.sqrt(abs(np.linalg.det(m[:2, :2])))
        for para in chars.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if cur and font.getlength(trial) > width > 0:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        x, y = _apply(m, [(0, 0)])[0]
        align = node.get("textAlignHorizontal", "LEFT")
        layer = Image.new("L", self.size, 0)
        d = ImageDraw.Draw(layer)
        lh = size * 1.2
        for i, line in enumerate(lines):
            lx = x * self.s
            if align == "CENTER":
                lx += (width - font.getlength(line)) / 2
            elif align == "RIGHT":
                lx += width - font.getlength(line)
            d.text((lx, y * self.s + i * lh), line, font=font, fill=255)
        self.paint({"type": "SOLID", "color": c, "opacity": fills[0].get("opacity", 1)}, layer, clip, node, m)


def render_fig(path, max_pixels=12_000_000):
    """Return ([(name, PIL.Image) per top-level frame], warnings); falls back to the embedded thumbnail."""
    message, images, thumb = load_fig(path)
    doc = _Doc(message, images)
    out, skipped = [], 0
    for page, node in doc.frames():
        w, h = node["size"]["x"], node["size"]["y"]
        scale = 2 if w * h * 4 <= max_pixels else 1
        r = _Renderer(doc, w, h, scale)
        try:
            r.draw(dict(node, transform=None), np.eye(3), Image.new("L", r.size, 255))
        except Exception:
            r.skipped += 1
        skipped += r.skipped
        bg = Image.new("RGBA", r.size, (255, 255, 255, 255))
        bg.alpha_composite(r.img)
        img = bg.convert("RGB")
        if scale != 1:
            img = img.resize((int(w), int(h)), Image.LANCZOS)
        out.append((f"{page} - {node.get('name', 'frame')}", img))
    if not out and thumb:
        out.append(("thumbnail", Image.open(io.BytesIO(thumb)).convert("RGB")))
    if not out:
        raise ValueError("No frames found in this Figma file")
    warnings = ["Frames are drawn by Unbolt, not Figma: effects, blend modes, component overrides and missing fonts may look different."]
    if skipped:
        warnings.append(f"{skipped} layer(s) could not be drawn and were skipped.")
    return out, warnings
