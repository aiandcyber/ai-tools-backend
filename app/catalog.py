from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str
    required: bool = False
    options: tuple[str, ...] = ()
    default: str = ""


@dataclass(frozen=True)
class Tool:
    id: str
    category: str
    title: str
    description: str
    accept: str = ""
    multiple: bool = False
    fields: tuple[Field, ...] = field(default_factory=tuple)

    def public(self) -> dict:
        data = asdict(self)
        data["fields"] = [asdict(item) for item in self.fields]
        return data


def _f(name: str, label: str, kind: str, **kwargs) -> Field:
    return Field(name, label, kind, **kwargs)


TOOLS: tuple[Tool, ...] = (
    Tool("pdf_merge", "pdf", "Combine PDFs", "Merge two or more PDF files into one, in the order uploaded.", ".pdf", True),
    Tool("pdf_compress", "pdf", "Compress PDF", "Rebuild each page as a smaller JPEG to reduce file size.", ".pdf", False, (
        _f("quality", "JPEG quality (40-90)", "number", default="60"),
    )),
    Tool("pdf_create", "pdf", "Create PDF", "Create a PDF from the title and text you enter.", "", False, (
        _f("title", "Title", "text", required=True),
        _f("body", "Text", "textarea", required=True),
    )),
    Tool("word_to_pdf", "pdf", "Word to PDF", "Convert a DOCX file to PDF. Requires LibreOffice in the container.", ".docx", False),
    Tool("model_to_pdf", "pdf", "3D to PDF", "Load an STL, OBJ, or PLY model and write a three-view PDF.", ".stl,.obj,.ply", False),
    Tool("pdf_pages", "pdf", "Pages", "Split, rotate, reorder, or delete PDF pages.", ".pdf", False, (
        _f("action", "Action", "select", required=True, options=("split", "rotate", "reorder", "delete"), default="split"),
        _f("pages", "Pages (1,3 or 2-4 or new order 3,1,2)", "text", default=""),
        _f("angle", "Rotate degrees", "select", options=("90", "180", "270"), default="90"),
    )),
    Tool("pdf_protect", "pdf", "Protect PDF", "Encrypt a PDF with a password.", ".pdf", False, (
        _f("password", "Password", "text", required=True),
    )),
    Tool("pdf_unlock", "pdf", "Unlock PDF", "Remove a PDF password.", ".pdf", False, (
        _f("password", "Password", "text", required=True),
    )),
    Tool("pdf_decorate", "pdf", "Page numbers and watermark", "Add a watermark and optional page numbers.", ".pdf", False, (
        _f("watermark", "Watermark text", "text", default="CONFIDENTIAL"),
        _f("page_numbers", "Page numbers", "select", options=("yes", "no"), default="yes"),
    )),
    Tool("pdf_extract_text", "pdf", "Extract text", "Extract the text from a PDF.", ".pdf", False),
    Tool("pdf_extract_images", "pdf", "Extract images", "Extract embedded images from a PDF into a ZIP.", ".pdf", False),
    Tool("images_to_pdf", "pdf", "Images to PDF", "Place one or more images into a single PDF.", "image/*", True),
    Tool("pdf_to_images", "pdf", "PDF to images", "Render each PDF page to a PNG inside a ZIP.", ".pdf", False),
    Tool("ocr", "pdf", "OCR", "Read text from a scanned PDF or image. Requires Tesseract in the container.", ".pdf,image/*", False),
    Tool("pdf_to_markdown", "pdf", "PDF to Markdown", "Turn extracted PDF text into a Markdown file.", ".pdf", False),
    Tool("docx_to_text", "office", "DOCX to text", "Convert a Word file to plain text or HTML.", ".docx", False, (
        _f("format", "Format", "select", options=("text", "html"), default="text"),
    )),
    Tool("xlsx_create", "office", "Create Excel", "Create an XLSX workbook from CSV text.", "", False, (
        _f("csv", "CSV text", "textarea", required=True),
        _f("sheet", "Sheet name", "text", default="Sheet1"),
    )),
    Tool("csv_to_xlsx", "office", "CSV to Excel", "Convert a CSV file to XLSX.", ".csv,text/csv", False),
    Tool("xlsx_to_csv", "office", "Excel to CSV", "Export the first worksheet to CSV.", ".xlsx", False),
    Tool("pptx_create", "office", "Create PowerPoint", "Create slides from text. Separate slides with a line that contains only ---.", "", False, (
        _f("slides", "Slide text", "textarea", required=True),
    )),
    Tool("xlsx_merge", "office", "Merge Excel", "Copy the first sheet of each workbook into one workbook.", ".xlsx", True),
    Tool("fill_template", "office", "Fill template", "Replace {{placeholders}} in a DOCX template using JSON.", ".docx", False, (
        _f("values", "JSON values", "textarea", required=True, default='{"name": "Ada"}'),
    )),
    Tool("image_compress", "image", "Compress image", "Re-save an image as JPEG or WebP at a lower quality.", "image/*", False, (
        _f("quality", "Quality (40-95)", "number", default="70"),
        _f("format", "Format", "select", options=("jpeg", "webp"), default="jpeg"),
    )),
    Tool("image_transform", "image", "Resize, crop, rotate", "Resize, crop, or rotate an image.", "image/*", False, (
        _f("action", "Action", "select", options=("resize", "crop", "rotate"), default="resize"),
        _f("width", "Width", "number", default=""),
        _f("height", "Height", "number", default=""),
        _f("angle", "Rotate degrees", "select", options=("90", "180", "270"), default="90"),
    )),
    Tool("image_convert", "image", "Convert image", "Convert between JPEG, PNG, WebP, BMP, and GIF.", "image/*", False, (
        _f("format", "Format", "select", required=True, options=("jpeg", "png", "webp", "bmp", "gif"), default="png"),
    )),
    Tool("image_watermark", "image", "Watermark image", "Draw text on an image.", "image/*", False, (
        _f("text", "Watermark", "text", required=True, default="DRAFT"),
    )),
    Tool("image_strip_exif", "image", "Strip EXIF", "Save the image without EXIF or GPS metadata.", "image/*", False),
    Tool("image_remove_bg", "image", "Remove background", "Remove the background. Uses rembg.", "image/*", False),
    Tool("favicon", "image", "Favicon", "Build a multi-size ICO from an image.", "image/*", False),
    Tool("palette", "image", "Color palette", "List the dominant colors in an image.", "image/*", False),
    Tool("media_convert", "media", "Convert media", "Convert audio or video with ffmpeg.", "audio/*,video/*", False, (
        _f("format", "Format", "select", required=True, options=("mp3", "wav", "m4a", "mp4", "webm"), default="mp3"),
    )),
    Tool("media_trim", "media", "Trim media", "Cut a clip between start and end timestamps (seconds).", "audio/*,video/*", False, (
        _f("start", "Start seconds", "number", default="0"),
        _f("end", "End seconds", "number", required=True),
    )),
    Tool("media_compress", "media", "Compress media", "Reduce audio bitrate or video CRF.", "audio/*,video/*", False, (
        _f("kind", "Kind", "select", options=("audio", "video"), default="video"),
    )),
    Tool("extract_audio", "media", "Extract audio", "Save the audio track of a video as MP3.", "video/*", False),
    Tool("tts", "media", "Text to speech", "Create an MP3 with edge-tts.", "", False, (
        _f("text", "Text", "textarea", required=True),
        _f("language", "Language", "select", options=("en", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
    )),
    Tool("stt", "media", "Speech to text", "Transcribe an audio file through OpenRouter.", "audio/*", False),
    Tool(
        "web_search",
        "search",
        "Search a Person or Topic",
        "Enterprise people/topic search across web, news, social, and science via SearXNG, with regional ranking for realtime-ai.",
        "",
        False,
        (
            _f("query", "Name or topic", "text", required=True),
            _f("mode", "Mode", "select", options=("auto", "person", "topic"), default="auto"),
            _f("region", "Region priority", "select", options=("SG", "IN", "MY", "US", "GB", "AU", "GLOBAL"), default="SG"),
            _f("language", "Language", "select", options=("en", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
            _f("interests", "Profile interests (comma-separated)", "text", default=""),
            _f("industry", "Profile industry", "text", default=""),
            _f("location", "Profile location", "text", default=""),
        ),
    ),
    Tool("zip_pack", "utility", "Create ZIP", "Pack the uploaded files into one ZIP.", "*", True),
    Tool("zip_extract", "utility", "Extract ZIP", "Extract a ZIP and pack the contents back into a new ZIP.", ".zip", False),
    Tool("data_convert", "utility", "Convert data", "Convert between JSON, YAML, and CSV.", ".json,.yaml,.yml,.csv,.txt", False, (
        _f("target", "Target", "select", required=True, options=("json", "yaml", "csv"), default="json"),
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("markdown_html", "utility", "Markdown to HTML", "Render Markdown to an HTML file.", ".md,.txt", False, (
        _f("text", "Or paste Markdown", "textarea", default=""),
    )),
    Tool("markdown_pdf", "utility", "Markdown to PDF", "Render Markdown text into a PDF.", ".md,.txt", False, (
        _f("text", "Or paste Markdown", "textarea", default=""),
    )),
    Tool("qr_generate", "utility", "QR code", "Create a QR code PNG.", "", False, (
        _f("text", "Text", "text", required=True),
    )),
    Tool("qr_scan", "utility", "Scan QR", "Read a QR code from an image.", "image/*", False),
    Tool("barcode_generate", "utility", "Barcode", "Create a Code128 barcode PNG.", "", False, (
        _f("text", "Text", "text", required=True),
    )),
    Tool("barcode_scan", "utility", "Scan barcode", "Read a barcode from an image.", "image/*", False),
    Tool("hash_text", "utility", "Hash", "Hash text or an uploaded file.", "*", False, (
        _f("algorithm", "Algorithm", "select", options=("sha256", "sha512", "md5"), default="sha256"),
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("base64_tool", "utility", "Base64", "Encode or decode text or a file.", "*", False, (
        _f("action", "Action", "select", options=("encode", "decode"), default="encode"),
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("uuid_tool", "utility", "UUID", "Generate a UUID.", "", False, (
        _f("count", "How many", "number", default="1"),
    )),
    Tool("text_diff", "utility", "Text diff", "Compare two pieces of text.", "", False, (
        _f("left", "Original", "textarea", required=True),
        _f("right", "Changed", "textarea", required=True),
    )),
    Tool("case_convert", "utility", "Change case", "Convert text case.", "", False, (
        _f("style", "Style", "select", options=("upper", "lower", "title", "snake", "kebab", "camel"), default="lower"),
        _f("text", "Text", "textarea", required=True),
    )),
    Tool("summarize", "ai", "Summarize", "Summarize pasted text or an uploaded PDF, DOCX, or text file.", ".pdf,.docx,.txt,.md", False, (
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("translate", "ai", "Translate", "Translate pasted text or an uploaded document.", ".pdf,.docx,.txt,.md", False, (
        _f("language", "Target language", "select", options=("en", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("rewrite", "ai", "Rewrite", "Rewrite pasted text or an uploaded document.", ".pdf,.docx,.txt,.md", False, (
        _f("instruction", "Instruction", "text", default="Make this clearer and shorter."),
        _f("text", "Or paste text", "textarea", default=""),
    )),
    Tool("generate_document", "ai", "Generate document", "Draft a PDF, DOCX, or PPTX from a request. Uses OpenRouter when a key is set.", "", False, (
        _f("request", "Request", "textarea", required=True),
        _f("format", "Format", "select", options=("pdf", "docx", "pptx"), default="docx"),
    )),
    Tool("classify", "ai", "Classify file", "Identify a file type and suggest the next tool.", "*", False),
)

BY_ID = {item.id: item for item in TOOLS}

CATEGORIES = (
    ("search", "Search"),
    ("pdf", "Documents / PDF"),
    ("office", "Office"),
    ("image", "Images"),
    ("media", "Audio / video"),
    ("utility", "Utilities"),
    ("ai", "AI"),
)
