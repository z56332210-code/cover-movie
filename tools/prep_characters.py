"""Cache character layers for the renderer: color + grayscale (saturation is a crossfade between the two),
full body at 0.55x and face close-ups at full resolution. Writes web/img/*.png and web/img/meta.json."""
import json
from PIL import Image, ImageOps

SCALE = 0.55
FACES = {"patient": (910, 880), "nurse": (1040, 880)}   # face centres in source pixels (measured)
FACE_BOX = 1100
meta = {}
for name, (fx, fy) in FACES.items():
    src = Image.open(f"assets/character/{name}.png").convert("RGBA")
    bbox = src.getchannel("A").getbbox()
    body = src.crop(bbox)
    body = body.resize((round(body.width * SCALE), round(body.height * SCALE)), Image.LANCZOS)
    face = src.crop((fx - FACE_BOX // 2, fy - FACE_BOX // 2 + 150, fx + FACE_BOX // 2, fy + FACE_BOX // 2 + 150))
    for tag, im in (("body", body), ("face", face)):
        im.save(f"web/img/{name}_{tag}.png", optimize=True)
        g = ImageOps.grayscale(im.convert("RGB")).convert("RGBA"); g.putalpha(im.getchannel("A"))
        g.save(f"web/img/{name}_{tag}_gray.png", optimize=True)
    meta[name] = dict(
        body=dict(w=body.width, h=body.height,
                  # position of the source canvas origin in body px; feet line shared by both drawings
                  ox=-bbox[0] * SCALE, oy=-bbox[1] * SCALE,
                  face=[(fx - bbox[0]) * SCALE, (fy - bbox[1]) * SCALE], face_r=180 * SCALE),
        face=dict(w=FACE_BOX, h=FACE_BOX, face=[FACE_BOX / 2, FACE_BOX / 2 - 150], face_r=180))
json.dump(meta, open("web/img/meta.json", "w"), indent=1)
print(json.dumps(meta, indent=1))
