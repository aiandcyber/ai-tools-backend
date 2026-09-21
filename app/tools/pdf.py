import shutil
import subprocess
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter


def merge_pdfs(files: list[Path], dest: Path) -> Path:
    writer = PdfWriter()
    for item in files:
        reader = PdfReader(str(item))
        for page in reader.pages:
            writer.add_page(page)
    with dest.open("wb") as handle:
        writer.write(handle)
    return dest


def compress_pdf(src: Path, dest: Path, quality: int) -> Path:
    quality = max(40, min(90, quality))
    source = pymupdf.open(src)
    deflated = dest.with_name(f"{dest.stem}-text.pdf")
    jpeg_path = dest.with_name(f"{dest.stem}-image.pdf")
    output = pymupdf.open()
    try:
        source.save(deflated, garbage=4, deflate=True, clean=True)
        for page in source:
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            image = pixmap.tobytes("jpeg", jpg_quality=quality)
            new_page = output.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=image)
        output.save(jpeg_path, garbage=4, deflate=True, clean=True)
    finally:
        output.close()
        source.close()
    best = min((deflated, jpeg_path), key=lambda path: path.stat().st_size)
    best.replace(dest)
    other = jpeg_path if best == deflated else deflated
    if other.exists():
        other.unlink()
    return dest


def create_pdf(dest: Path, title: str, body: str) -> Path:
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), title or "Document", fontsize=18)
        rect = pymupdf.Rect(72, 110, page.rect.width - 72, page.rect.height - 72)
        page.insert_textbox(rect, body, fontsize=11)
        doc.save(dest)
    finally:
        doc.close()
    return dest


def word_to_pdf(src: Path, out_dir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice is not installed. The Fargate image includes it.")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(src)],
        check=True,
        timeout=180,
        capture_output=True,
    )
    dest = out_dir / f"{src.stem}.pdf"
    if not dest.exists():
        raise RuntimeError("LibreOffice did not produce a PDF")
    return dest


def model_to_pdf(src: Path, dest: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import trimesh

    loaded = trimesh.load(src, force="mesh")
    mesh = loaded.dump(concatenate=True) if isinstance(loaded, trimesh.Scene) else loaded
    if len(mesh.faces) > 80000 and hasattr(mesh, "simplify_quadric_decimation"):
        try:
            mesh = mesh.simplify_quadric_decimation(80000)
        except Exception:
            pass
    figure = plt.figure(figsize=(8.27, 11.69))
    for index, (elev, azim, label) in enumerate(((20, 35, "View 1"), (0, 0, "Front"), (90, 0, "Top")), start=1):
        axis = figure.add_subplot(3, 1, index, projection="3d")
        axis.plot_trisurf(
            mesh.vertices[:, 0],
            mesh.vertices[:, 1],
            mesh.vertices[:, 2],
            triangles=mesh.faces,
            color="#4f46e5",
            linewidth=0,
            antialiased=False,
        )
        axis.set_title(label)
        axis.view_init(elev=elev, azim=azim)
    figure.tight_layout()
    figure.savefig(dest, format="pdf")
    plt.close(figure)
    return dest


def _reader(src: Path) -> PdfReader:
    return PdfReader(str(src))


def _parse_pages(spec: str, count: int) -> list[int]:
    if not spec.strip():
        return list(range(count))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(part) - 1)
    for page in pages:
        if page < 0 or page >= count:
            raise ValueError(f"Page out of range: {page + 1}")
    return pages


def transform_pages(src: Path, dest: Path, action: str, pages: str, angle: int) -> list[Path]:
    reader = _reader(src)
    indexes = _parse_pages(pages, len(reader.pages))
    if action == "split":
        outputs: list[Path] = []
        for index in indexes:
            writer = PdfWriter()
            writer.add_page(reader.pages[index])
            part = dest.with_name(f"{dest.stem}-page-{index + 1}.pdf")
            with part.open("wb") as handle:
                writer.write(handle)
            outputs.append(part)
        return outputs
    writer = PdfWriter()
    if action == "delete":
        drop = set(indexes)
        chosen = [i for i in range(len(reader.pages)) if i not in drop]
    elif action == "reorder":
        chosen = indexes
    else:
        chosen = list(range(len(reader.pages)))
    rotate_set = set(indexes) if action == "rotate" else set()
    for index in chosen:
        page = reader.pages[index]
        if index in rotate_set:
            page.rotate(angle)
        writer.add_page(page)
    with dest.open("wb") as handle:
        writer.write(handle)
    return [dest]


def protect_pdf(src: Path, dest: Path, password: str) -> Path:
    reader = _reader(src)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    with dest.open("wb") as handle:
        writer.write(handle)
    return dest


def unlock_pdf(src: Path, dest: Path, password: str) -> Path:
    reader = _reader(src)
    if reader.is_encrypted and reader.decrypt(password) == 0:
        raise ValueError("Wrong password")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with dest.open("wb") as handle:
        writer.write(handle)
    return dest


def decorate_pdf(src: Path, dest: Path, watermark: str, page_numbers: bool) -> Path:
    doc = pymupdf.open(src)
    try:
        for number, page in enumerate(doc, start=1):
            if watermark:
                page.insert_text(
                    (72, page.rect.height / 2),
                    watermark,
                    fontsize=42,
                    color=(0.7, 0.7, 0.7),
                    rotate=30,
                )
            if page_numbers:
                page.insert_text((page.rect.width - 72, page.rect.height - 36), str(number), fontsize=11)
        doc.save(dest)
    finally:
        doc.close()
    return dest


def extract_text(src: Path) -> str:
    doc = pymupdf.open(src)
    try:
        return "\n\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def extract_images(src: Path, out_dir: Path) -> list[Path]:
    doc = pymupdf.open(src)
    saved: list[Path] = []
    try:
        for page_index, page in enumerate(doc, start=1):
            for image_index, image in enumerate(page.get_images(full=True), start=1):
                info = doc.extract_image(image[0])
                dest = out_dir / f"page-{page_index}-{image_index}.{info['ext']}"
                dest.write_bytes(info["image"])
                saved.append(dest)
    finally:
        doc.close()
    if not saved:
        raise ValueError("No embedded images found")
    return saved


def images_to_pdf(files: list[Path], dest: Path) -> Path:
    doc = pymupdf.open()
    try:
        for item in files:
            pixmap = pymupdf.Pixmap(str(item))
            page = doc.new_page(width=pixmap.width, height=pixmap.height)
            page.insert_image(page.rect, filename=str(item))
        doc.save(dest)
    finally:
        doc.close()
    return dest


def pdf_to_images(src: Path, out_dir: Path) -> list[Path]:
    doc = pymupdf.open(src)
    saved: list[Path] = []
    try:
        for index, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            dest = out_dir / f"page-{index}.png"
            pixmap.save(dest)
            saved.append(dest)
    finally:
        doc.close()
    return saved


def ocr_file(src: Path) -> str:
    import pytesseract
    from PIL import Image

    lang = "eng+chi_sim+hin+tam+mal+kan+tel"
    if src.suffix.lower() == ".pdf":
        doc = pymupdf.open(src)
        chunks: list[str] = []
        try:
            for index, page in enumerate(doc, start=1):
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                chunks.append(f"# Page {index}\n\n{pytesseract.image_to_string(image, lang=lang)}")
        finally:
            doc.close()
        return "\n\n".join(chunks)
    return pytesseract.image_to_string(Image.open(src), lang=lang)


def pdf_to_markdown(src: Path) -> str:
    text = extract_text(src).strip()
    if not text:
        text = "(no extractable text)"
    return f"# {src.stem}\n\n{text}\n"
