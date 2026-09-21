import base64
import csv
import difflib
import hashlib
import io
import json
import re
import uuid
from pathlib import Path

import qrcode
import yaml
from barcode import Code128
from barcode.writer import ImageWriter

from app.workspace import safe_extract, zip_paths


def pack_zip(files: list[Path], dest: Path) -> Path:
    return zip_paths(files, dest)


def extract_zip(src: Path, out_dir: Path, dest: Path) -> Path:
    extracted = safe_extract(src, out_dir / "unzipped")
    files = [item for item in extracted if item.is_file()]
    if not files:
        raise ValueError("ZIP is empty")
    return zip_paths(files, dest)


def convert_data(text: str, target: str) -> str:
    parsed = _parse_data(text)
    if target == "json":
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    if target == "yaml":
        return yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
    rows = parsed if isinstance(parsed, list) else [parsed]
    if rows and isinstance(rows[0], dict):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
    raise ValueError("CSV output needs a list of objects")


def _parse_data(text: str):
    stripped = text.strip()
    if not stripped:
        raise ValueError("No data")
    if stripped[0] in "[{":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return yaml.safe_load(stripped)
    if "," in stripped.splitlines()[0]:
        return list(csv.DictReader(io.StringIO(stripped)))
    return yaml.safe_load(stripped)


def markdown_to_html(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("### "):
            lines.append(f"<h3>{_escape(line[4:])}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{_escape(line[3:])}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{_escape(line[2:])}</h1>")
        elif line.strip() == "":
            lines.append("")
        else:
            lines.append(f"<p>{_escape(line)}</p>")
    body = "\n".join(lines)
    return f"<!doctype html><html><head><meta charset=\"utf-8\"></head><body>{body}</body></html>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def qr_png(text: str, dest: Path) -> Path:
    image = qrcode.make(text)
    image.save(dest)
    return dest


def scan_qr(src: Path) -> str:
    import cv2

    image = cv2.imread(str(src))
    if image is None:
        raise ValueError("Could not read image")
    detector = cv2.QRCodeDetector()
    value, _, _ = detector.detectAndDecode(image)
    if not value:
        raise ValueError("No QR code found")
    return value


def barcode_png(text: str, dest: Path) -> Path:
    code = Code128(text, writer=ImageWriter())
    saved = Path(code.save(str(dest.with_suffix(""))))
    if saved != dest and saved.exists():
        saved.replace(dest)
    return dest


def scan_barcode(src: Path) -> str:
    import cv2

    image = cv2.imread(str(src))
    if image is None:
        raise ValueError("Could not read image")
    if not hasattr(cv2, "barcode"):
        raise RuntimeError("This OpenCV build has no barcode detector")
    detector = cv2.barcode.BarcodeDetector()
    ok, decoded, _, _ = detector.detectAndDecode(image)
    values = [item for item in (decoded or []) if item]
    if not ok or not values:
        raise ValueError("No barcode found")
    return "\n".join(values)


def hash_bytes(data: bytes, algorithm: str) -> str:
    digest = getattr(hashlib, algorithm)(data).hexdigest()
    return f"{algorithm} {digest}\n"


def base64_convert(data: bytes, action: str) -> bytes:
    if action == "encode":
        return base64.b64encode(data)
    return base64.b64decode(data)


def make_uuids(count: int) -> str:
    count = max(1, min(count, 50))
    return "\n".join(str(uuid.uuid4()) for _ in range(count)) + "\n"


def diff_text(left: str, right: str) -> str:
    return "".join(difflib.unified_diff(
        left.splitlines(keepends=True),
        right.splitlines(keepends=True),
        fromfile="original",
        tofile="changed",
    )) or "No differences\n"


def change_case(text: str, style: str) -> str:
    if style == "upper":
        return text.upper()
    if style == "lower":
        return text.lower()
    if style == "title":
        return text.title()
    words = re.findall(r"[A-Za-z0-9]+", text)
    if style == "snake":
        return "_".join(word.lower() for word in words)
    if style == "kebab":
        return "-".join(word.lower() for word in words)
    if style == "camel" and words:
        head, *tail = words
        return head.lower() + "".join(word.title() for word in tail)
    return text
