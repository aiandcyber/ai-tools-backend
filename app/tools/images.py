from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def compress_image(src: Path, dest: Path, quality: int, fmt: str) -> Path:
    quality = max(40, min(95, quality))
    image = Image.open(src)
    if fmt == "jpeg":
        image = image.convert("RGB")
        image.save(dest, format="JPEG", quality=quality, optimize=True)
    else:
        image.save(dest, format="WEBP", quality=quality)
    return dest


def transform_image(src: Path, dest: Path, action: str, width: str, height: str, angle: int) -> Path:
    image = Image.open(src)
    if action == "rotate":
        image = image.rotate(-angle, expand=True)
    elif action == "resize":
        size = (
            int(width) if width else image.width,
            int(height) if height else image.height,
        )
        image = image.resize(size)
    else:
        left = 0
        top = 0
        right = int(width) if width else image.width
        bottom = int(height) if height else image.height
        image = image.crop((left, top, min(right, image.width), min(bottom, image.height)))
    image.save(dest)
    return dest


def convert_image(src: Path, dest: Path, fmt: str) -> Path:
    image = Image.open(src)
    pil_format = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP", "gif": "GIF"}[fmt]
    if pil_format == "JPEG":
        image = image.convert("RGB")
    image.save(dest, format=pil_format)
    return dest


def watermark_image(src: Path, dest: Path, text: str) -> Path:
    image = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default(36)
    draw.text((40, image.height // 2), text, fill=(255, 255, 255, 140), font=font)
    Image.alpha_composite(image, overlay).convert("RGB").save(dest, quality=90)
    return dest


def strip_exif(src: Path, dest: Path) -> Path:
    image = Image.open(src)
    clean = Image.new(image.mode, image.size)
    clean.putdata(list(image.getdata()))
    suffix = dest.suffix.lower().lstrip(".")
    fmt = "JPEG" if suffix in {"jpg", "jpeg"} else suffix.upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt == "JPEG":
        clean = clean.convert("RGB")
    clean.save(dest, format=fmt)
    return dest


def remove_background(src: Path, dest: Path) -> Path:
    from rembg import remove

    dest.write_bytes(remove(src.read_bytes()))
    return dest


def favicon(src: Path, dest: Path) -> Path:
    image = Image.open(src).convert("RGBA")
    image.save(dest, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    return dest


def palette(src: Path) -> str:
    image = Image.open(src).convert("RGB")
    image.thumbnail((120, 120))
    counts = Counter(image.getdata())
    lines = ["color,count"]
    for (red, green, blue), count in counts.most_common(8):
        lines.append(f"#{red:02x}{green:02x}{blue:02x},{count}")
    return "\n".join(lines) + "\n"
