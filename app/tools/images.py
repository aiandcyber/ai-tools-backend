from collections import Counter
from pathlib import Path

from PIL import ExifTags, Image, ImageDraw, ImageFont


def _gps_to_degrees(value) -> float | None:
    try:
        degrees, minutes, seconds = value
        def _num(part) -> float:
            if hasattr(part, "numerator") and hasattr(part, "denominator"):
                return float(part.numerator) / float(part.denominator or 1)
            if isinstance(part, tuple) and len(part) == 2:
                return float(part[0]) / float(part[1] or 1)
            return float(part)
        return _num(degrees) + _num(minutes) / 60.0 + _num(seconds) / 3600.0
    except Exception:
        return None


def privacy_report(src: Path) -> tuple[str, bool]:
    """Return a human-readable EXIF/privacy report and whether sensitive tags were found."""
    image = Image.open(src)
    raw = image.getexif()
    if not raw:
        return "No EXIF or privacy metadata found in this image.", False

    tag_names = {index: name for index, name in ExifTags.TAGS.items()}
    gps_names = {index: name for index, name in ExifTags.GPSTAGS.items()}
    lines: list[str] = ["Image privacy report", f"File: {src.name}", ""]
    sensitive = False
    interesting = {
        "Make",
        "Model",
        "Software",
        "DateTime",
        "DateTimeOriginal",
        "DateTimeDigitized",
        "Artist",
        "Copyright",
        "ImageDescription",
        "Orientation",
        "BodySerialNumber",
        "LensModel",
        "LensMake",
    }

    for tag_id, value in raw.items():
        name = tag_names.get(tag_id, str(tag_id))
        if name not in interesting:
            continue
        if name in {
            "Artist",
            "Copyright",
            "ImageDescription",
            "BodySerialNumber",
            "Make",
            "Model",
            "Software",
            "DateTime",
            "DateTimeOriginal",
            "DateTimeDigitized",
            "LensModel",
            "LensMake",
        }:
            sensitive = True
        lines.append(f"{name}: {value}")

    # Nested EXIF IFD (timestamps, lens, etc.)
    try:
        exif_ifd = raw.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        exif_ifd = {}
    for tag_id, value in (exif_ifd or {}).items():
        name = tag_names.get(tag_id, str(tag_id))
        if name not in interesting:
            continue
        if any(existing.startswith(f"{name}:") for existing in lines):
            continue
        if name in interesting - {"Orientation"}:
            sensitive = True
        lines.append(f"{name}: {value}")

    # GPS IFD
    try:
        gps_ifd = raw.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:
        gps_ifd = {}
    if gps_ifd:
        sensitive = True
        lines.append("GPS / location:")
        lat = lon = None
        lat_ref = lon_ref = None
        for gps_id, gps_value in gps_ifd.items():
            gps_name = gps_names.get(gps_id, str(gps_id))
            if gps_name == "GPSLatitude":
                lat = _gps_to_degrees(gps_value)
            elif gps_name == "GPSLongitude":
                lon = _gps_to_degrees(gps_value)
            elif gps_name == "GPSLatitudeRef":
                lat_ref = str(gps_value)
            elif gps_name == "GPSLongitudeRef":
                lon_ref = str(gps_value)
            else:
                lines.append(f"  {gps_name}: {gps_value}")
        if lat is not None and lon is not None:
            if lat_ref == "S":
                lat = -lat
            if lon_ref == "W":
                lon = -lon
            lines.append(f"  Latitude: {lat:.6f}")
            lines.append(f"  Longitude: {lon:.6f}")
        lines.append("")

    if len(lines) <= 3:
        return "No notable privacy metadata found in this image.", False
    if not sensitive:
        lines.append("")
        lines.append("No high-risk privacy fields (GPS, camera identity, timestamps) were detected.")
    else:
        lines.append("")
        lines.append("Privacy-related metadata was found. Use Remove Your Privacy to strip it.")
    return "\n".join(lines).strip() + "\n", sensitive


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
