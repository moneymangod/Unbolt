"""Draw Unbolt's icon (an open padlock) into assets/icon.ico."""
import os

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=220, fill=(47, 111, 237, 255))
d.rounded_rectangle([250, 450, 774, 840], radius=70, fill="white")
d.ellipse([460, 580, 564, 684], fill=(47, 111, 237, 255))
d.rounded_rectangle([488, 640, 536, 760], radius=20, fill=(47, 111, 237, 255))
d.arc([320, 160, 704, 560], start=180, end=320, fill="white", width=70)   # shackle, lifted on the right
d.rectangle([320, 350, 390, 450], fill="white")                           # left leg
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(out, exist_ok=True)
img.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((512, 512), Image.LANCZOS).save(os.path.join(out, "icon.png"))
