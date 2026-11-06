---
name: image-tools
description: Image compress, convert, watermark, remove background, favicon, and QR/barcode scan or create.
---

# Image tools

Use `run_image_tool` with the matching `tool_id` and uploaded image when required.

## Tool ids

- `image_compress`, `image_convert`
- `qr_scan` / `qr_generate` — Scan QR Code / Create QR Code
- `barcode_scan` / `barcode_generate` — Scan Barcode / Create Barcode
- `image_watermark`
- `image_remove_bg` — Remove background
- `favicon` — Create Icon (Favicon)

Prefer lossless intent when the user asks to preserve quality; otherwise use the tool defaults.
