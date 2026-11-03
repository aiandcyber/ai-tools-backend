"""Shared upload gate: type, size, basic static virus scan, quarantine write."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from app import config

_log = logging.getLogger("uvicorn.error")

MB = 1024 * 1024

# Per-category defaults when a tool leaves max_upload_bytes at 0.
CATEGORY_MAX_UPLOAD_BYTES: dict[str, int] = {
    "pdf": 40 * MB,
    "image": 20 * MB,
    "media": 80 * MB,
    "utility": 15 * MB,
    "ai": 20 * MB,
    "search": 15 * MB,
    "safety": 32 * MB,
}

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
DENY_SHA256 = {EICAR_SHA256}

# extension -> accepted when accept lists this ext or matching mime family
_EXT_MIME_HINTS: dict[str, tuple[str, ...]] = {
    ".pdf": ("application/pdf",),
    ".png": ("image/png",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
    ".gif": ("image/gif",),
    ".webp": ("image/webp",),
    ".bmp": ("image/bmp",),
    ".tif": ("image/tiff",),
    ".tiff": ("image/tiff",),
    ".mp3": ("audio/mpeg", "audio/mp3"),
    ".wav": ("audio/wav", "audio/x-wav", "audio/wave"),
    ".m4a": ("audio/mp4", "audio/m4a"),
    ".ogg": ("audio/ogg",),
    ".flac": ("audio/flac",),
    ".mp4": ("video/mp4",),
    ".webm": ("video/webm", "audio/webm"),
    ".mov": ("video/quicktime",),
    ".mkv": ("video/x-matroska",),
    ".avi": ("video/x-msvideo",),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    ".doc": ("application/msword",),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
    ".txt": ("text/plain",),
    ".md": ("text/markdown", "text/plain"),
    ".csv": ("text/csv", "text/plain"),
    ".json": ("application/json", "text/plain"),
    ".zip": ("application/zip",),
}


@dataclass
class GateResult:
    ok: bool
    stage: str
    detail: str = ""
    labels: list[str] | None = None


def resolved_max_upload_bytes(tool_id: str, category: str, tool_max: int = 0) -> int:
    env_map = getattr(config, "MAX_UPLOAD_BYTES_BY_TOOL", {}) or {}
    if tool_id and tool_id in env_map and env_map[tool_id] > 0:
        return int(env_map[tool_id])
    if tool_max and tool_max > 0:
        return int(tool_max)
    if category in CATEGORY_MAX_UPLOAD_BYTES:
        return CATEGORY_MAX_UPLOAD_BYTES[category]
    return int(config.MAX_UPLOAD_BYTES)


def quarantine_root() -> Path:
    root = config.JOB_ROOT / "quarantine"
    root.mkdir(parents=True, exist_ok=True)
    # Best-effort: owner-only access on Unix.
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_accept(accept: str) -> tuple[set[str], set[str], bool]:
    """Return (extensions with dot, mime prefixes/exact, allow_any)."""
    raw = (accept or "").strip()
    if not raw or raw == "*/*" or raw == "*":
        return set(), set(), True
    exts: set[str] = set()
    mimes: set[str] = set()
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token in {"*", "*/*"}:
            return set(), set(), True
        if token.startswith("."):
            exts.add(token)
        elif "/" in token:
            mimes.add(token)
        else:
            exts.add(f".{token}")
    return exts, mimes, False


def _ext(name: str) -> str:
    return Path(name or "").suffix.lower()


def check_type(filename: str, content_type: str, accept: str, data: bytes) -> GateResult:
    exts, mimes, allow_any = parse_accept(accept)
    if allow_any:
        return GateResult(True, "type")
    ext = _ext(filename)
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ext and ext in exts:
        return GateResult(True, "type")
    if ctype:
        for mime in mimes:
            if mime.endswith("/*"):
                if ctype.startswith(mime[:-1]):
                    return GateResult(True, "type")
            elif ctype == mime:
                return GateResult(True, "type")
    # MIME family from accept image/* / audio/* / video/* already handled.
    # Fall back: extension known for an accepted mime family.
    for mime in mimes:
        if mime.endswith("/*"):
            family = mime.split("/", 1)[0]
            hints = _EXT_MIME_HINTS.get(ext, ())
            if any(h.startswith(family + "/") for h in hints):
                return GateResult(True, "type")
            # Magic sniff for common families
            if family == "image" and data[:3] == b"\xff\xd8\xff":
                return GateResult(True, "type")
            if family == "image" and data[:8] == b"\x89PNG\r\n\x1a\n":
                return GateResult(True, "type")
            if family == "audio" and (data[:3] == b"ID3" or data[:2] == b"\xff\xfb"):
                return GateResult(True, "type")
            if family == "video" and data[4:8] == b"ftyp":
                return GateResult(True, "type")
    allowed = ", ".join(sorted(exts) + sorted(mimes)) or "defined types"
    return GateResult(False, "type", f"File type not allowed. Allowed: {allowed}")


def check_size(size: int, max_bytes: int) -> GateResult:
    if size <= 0:
        return GateResult(False, "size", "Empty file")
    if size > max_bytes:
        mb = max_bytes / MB
        return GateResult(False, "size", f"File is too large. Maximum is {mb:.0f} MB")
    return GateResult(True, "size")


def _clamav_scan(path: Path) -> GateResult | None:
    binary = shutil.which("clamdscan") or shutil.which("clamscan")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "--no-summary", str(path)],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        _log.warning("clamav scan failed: %s", exc)
        return None
    # 0 clean, 1 virus, 2 error
    if proc.returncode == 0:
        return GateResult(True, "scan", labels=["clamav:clean"])
    if proc.returncode == 1:
        return GateResult(False, "scan", "Basic virus scan failed", labels=["virus", "clamav"])
    return None


def basic_scan(data: bytes, *, allow_executables: bool = False) -> GateResult:
    """Static basic scan. Never executes the sample."""
    labels: list[str] = []
    sha = _sha256(data)
    if data.startswith(EICAR) or EICAR in data[:4096] or sha in DENY_SHA256:
        return GateResult(False, "scan", "Basic virus scan failed", labels=["virus"])
    is_pe = data[:2] == b"MZ"
    is_elf = data[:4] == b"\x7fELF"
    is_macho = data[:4] in {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}
    if is_pe or is_elf or is_macho:
        labels.append("executable")
        if not allow_executables:
            return GateResult(
                False,
                "scan",
                "Executable files are not allowed for this tool",
                labels=labels,
            )
    # Optional ClamAV via temp path handled by caller after write.
    return GateResult(True, "scan", labels=labels)


def accept_allows_executables(accept: str) -> bool:
    exts, mimes, allow_any = parse_accept(accept)
    if allow_any:
        return True
    exec_exts = {".exe", ".dll", ".so", ".dylib", ".bin", ".apk", ".dex"}
    if exts & exec_exts:
        return True
    return False


def gate_upload(
    *,
    filename: str,
    content_type: str,
    data: bytes,
    accept: str,
    max_bytes: int,
) -> GateResult:
    type_result = check_type(filename, content_type, accept, data)
    if not type_result.ok:
        return type_result
    size_result = check_size(len(data), max_bytes)
    if not size_result.ok:
        return size_result
    scan_result = basic_scan(data, allow_executables=accept_allows_executables(accept))
    if not scan_result.ok:
        return scan_result
    return GateResult(True, "ready", labels=scan_result.labels or [])


def write_quarantine(data: bytes, filename: str) -> Path:
    """Write into quarantine; strip path components from filename."""
    safe = re.sub(r"[^\w.\-()+ ]+", "_", Path(filename).name)[:120] or "upload.bin"
    dest = quarantine_root() / f"{uuid.uuid4().hex}-{safe}"
    dest.write_bytes(data)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    clam = _clamav_scan(dest)
    if clam is not None and not clam.ok:
        dest.unlink(missing_ok=True)
        raise ValueError(clam.detail or "Basic virus scan failed")
    return dest


def delete_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
