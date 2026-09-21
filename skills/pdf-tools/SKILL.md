---
name: pdf-tools
description: PDF and document operations — merge, compress, create, Word-to-PDF, pages, protect, watermark, OCR, extract text/images, 3D-to-PDF.
---

# PDF / Documents tools

## Workflow

1. Confirm an uploaded file exists when the tool needs one.
2. Call `run_pdf_tool` with the correct `tool_id` and `options_json`.
3. Return the tool message; downloads are attached by the backend.

## Common tool ids

- `pdf_merge` — two or more PDFs
- `pdf_compress` — options: `quality` (40–90)
- `pdf_create` — options: `title`, `body`
- `word_to_pdf` — needs `.docx`
- `model_to_pdf` — STL/OBJ/PLY
- `pdf_pages` — `action` split|rotate|reorder|delete; `pages`; `angle`
- `pdf_protect` / `pdf_unlock` — password options
- `pdf_watermark` — text watermark / page numbers
- `pdf_extract_text`, `pdf_extract_images`, `pdf_ocr`
- `images_to_pdf`, `pdf_to_images`

Prefer the specialist tool that matches the user ask; do not claim success without a tool result.
