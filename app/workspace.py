import json
import shutil
import uuid
import zipfile
from pathlib import Path

from app import config


def ensure_jobs() -> Path:
    config.JOB_ROOT.mkdir(parents=True, exist_ok=True)
    return config.JOB_ROOT


def publish(path: Path) -> dict:
    root = ensure_jobs()
    token = uuid.uuid4().hex
    dest_dir = root / token
    dest_dir.mkdir(parents=True, exist_ok=False)
    dest = dest_dir / path.name
    shutil.copy2(path, dest)
    return {"name": dest.name, "url": f"/api/files/{token}/{dest.name}"}


def resolve_download(token: str, name: str) -> Path:
    path = (config.JOB_ROOT / token / name).resolve()
    root = config.JOB_ROOT.resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError(name)
    return path


def write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def zip_paths(paths: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in paths:
            archive.write(item, arcname=item.name)
    return dest


def safe_extract(archive: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if dest.resolve() not in target.parents and target != dest.resolve():
                raise ValueError(f"Blocked unsafe path: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            extracted.append(target)
    return extracted


def loads_json(text: str) -> dict:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("JSON must be an object")
    return value
