---
name: pdf-tools
description: PDF operations — merge, compress, unlock/protect, OCR, pages, extract text/images, images to PDF, watermark.
---

# PDF / Documents tools

## Workflow

1. Confirm an uploaded file exists when the tool needs one.
2. Call `run_pdf_tool` with the correct `tool_id` and `options_json`.
3. Return the tool message; downloads are attached by the backend.

## Common tool ids

- `pdf_merge` — two or more PDFs
- `pdf_compress`
- `pdf_unlock` / `pdf_protect` — password options
- `ocr` — Text From Scanned Doc (OCR)
- `pdf_pages` — `action` split|rotate|reorder|delete; `pages`; `angle` only for rotate
- `pdf_extract_text`, `pdf_extract_images`
- `images_to_pdf`, `pdf_to_images`
- `pdf_decorate` — Add Watermark into PDF (optional page numbers)

Prefer the specialist tool that matches the user ask; do not claim success without a tool result.
