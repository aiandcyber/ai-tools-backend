from pathlib import Path

import httpx

from app import config
from app.tools import office, pdf

LANG = {
    "en": "English",
    "yue": "Cantonese",
    "zh": "Chinese",
    "ta": "Tamil",
    "hi": "Hindi",
    "ml": "Malayalam",
    "kn": "Kannada",
    "te": "Telugu",
}


def source_text(files: list[Path], pasted: str) -> str:
    if pasted.strip():
        return pasted
    if not files:
        raise ValueError("Paste text or upload a file")
    src = files[0]
    suffix = src.suffix.lower()
    if suffix == ".pdf":
        return pdf.extract_text(src)
    if suffix == ".docx":
        return office.docx_to_text(src, "text")
    return src.read_text(encoding="utf-8", errors="replace")


def complete(system: str, user: str) -> str:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    response = httpx.post(
        f"{config.OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user[:30000]},
            ],
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text[:800])
    return response.json()["choices"][0]["message"]["content"]


def summarize(text: str) -> str:
    return complete("Summarize the user's document in concise Markdown.", text)


def translate(text: str, language: str, source_language: str = "auto") -> str:
    target = LANG.get(language, language)
    source = (source_language or "auto").strip().lower()
    if source in {"", "auto", "detect"}:
        system = (
            f"Detect the language of the user's text and translate it into {target}. "
            "Return only the translation."
        )
    else:
        source_name = LANG.get(source, source_language)
        system = (
            f"Translate the user's text from {source_name} into {target}. "
            "Return only the translation."
        )
    return complete(system, text)


def rewrite(text: str, instruction: str) -> str:
    return complete(instruction or "Rewrite this more clearly.", text)


def draft(request: str, fmt: str, template_hint: str = "") -> str:
    if not config.OPENROUTER_API_KEY:
        return request
    if fmt == "pptx":
        system = "Write slide text. Separate slides with a line containing only ---. First line of each slide is the title."
    else:
        system = "Write a clear document from the request. Use plain paragraphs."
    if template_hint.strip():
        system += f" Follow this template or style guidance closely:\n{template_hint.strip()[:8000]}"
    return complete(system, request)


def classify(src: Path) -> str:
    kind = src.suffix.lower() or "unknown"
    suggestion = {
        ".pdf": "pdf_compress, pdf_merge, pdf_extract_text, ocr",
        ".docx": "word_to_pdf, docx_to_text, docx_merge",
        ".xlsx": "xlsx_to_csv, xlsx_merge",
        ".pptx": "pptx_merge, pptx_create",
        ".csv": "csv_to_xlsx",
        ".png": "image_compress, image_convert, image_remove_bg",
        ".jpg": "image_compress, image_convert",
        ".jpeg": "image_compress, image_convert",
        ".mp4": "media_compress, extract_audio, media_trim",
        ".mp3": "media_convert, media_trim",
        ".zip": "zip_extract",
    }.get(kind, "hash_text")
    detail = f"Extension: {kind}\nSuggested tools: {suggestion}\n"
    if not config.OPENROUTER_API_KEY:
        return detail
    try:
        note = complete("Suggest the single best next tool id. Reply with one sentence.", f"File name: {src.name}")
    except Exception as exc:
        note = f"OpenRouter note: {exc}"
    return detail + note + "\n"
