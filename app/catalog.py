from dataclasses import asdict, dataclass, field

from app.upload_security import resolved_max_upload_bytes


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
    # 0 = use category default from upload_security.CATEGORY_MAX_UPLOAD_BYTES
    max_upload_bytes: int = 0

    def public(self) -> dict:
        data = asdict(self)
        data["fields"] = [asdict(item) for item in self.fields]
        data["max_upload_bytes"] = resolved_max_upload_bytes(
            self.id, self.category, self.max_upload_bytes
        )
        return data


def _f(name: str, label: str, kind: str, **kwargs) -> Field:
    return Field(name, label, kind, **kwargs)


TOOLS: tuple[Tool, ...] = (
    Tool(
        "summarize",
        "pdf",
        "Summarize Text",
        "Summarize pasted text or an uploaded PDF, DOCX, or text file.",
        ".pdf,.docx,.txt,.md",
        False,
        (
            _f("text", "Or paste text", "textarea", default=""),
        ),
    ),
    Tool(
        "translate",
        "pdf",
        "Translate Text",
        "Translate pasted text or an uploaded document.",
        ".pdf,.docx,.txt,.md",
        False,
        (
            _f("source_language", "From language", "select", options=("auto", "en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="auto"),
            _f("language", "Target language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
            _f("text", "Or paste text", "textarea", default=""),
        ),
    ),
    Tool("pdf_merge", "pdf", "Combine PDFs", "Merge two or more PDF files into one, in the order uploaded.", ".pdf", True),
    Tool("pdf_compress", "pdf", "Compress PDF", "Reduce PDF file size. Output stays a PDF.", ".pdf", False),
    Tool("pdf_unlock", "pdf", "Unlock PDF", "Remove a PDF password.", ".pdf", False, (
        _f("password", "Password", "text", required=True),
    )),
    Tool("pdf_protect", "pdf", "Protect PDF", "Encrypt a PDF with a password.", ".pdf", False, (
        _f("password", "Password", "text", required=True),
    )),
    Tool(
        "ocr",
        "pdf",
        "Text From Scanned Doc (OCR)",
        "Read text from a scanned PDF or image, Optical Character Recognition.",
        ".pdf,image/*",
        False,
    ),
    Tool("pdf_pages", "pdf", "Split, Reorder, Delete PDF Pages", "Split, rotate, reorder, or delete PDF pages.", ".pdf", False, (
        _f("action", "Action", "select", required=True, options=("split", "rotate", "reorder", "delete"), default="split"),
        _f("pages", "Pages (1,3 or 2-4 or new order 3,1,2)", "text", default=""),
        _f("angle", "Rotate degrees", "select", options=("90", "180", "270"), default="90"),
    )),
    Tool("pdf_extract_text", "pdf", "Extract PDF Text", "Extract the text from a PDF.", ".pdf", False),
    Tool("pdf_extract_images", "pdf", "Extract PDF Images", "Extract embedded images from a PDF into a ZIP.", ".pdf", False),
    Tool("images_to_pdf", "pdf", "Images to PDF", "Place one or more images into a single PDF.", "image/*", True),
    Tool("pdf_to_images", "pdf", "PDF to images", "Render each PDF page to a PNG inside a ZIP.", ".pdf", False),
    Tool("pdf_decorate", "pdf", "Add Watermark into PDF", "Add a watermark and optional page numbers.", ".pdf", False, (
        _f("watermark", "Watermark text", "text", default="CONFIDENTIAL"),
        _f("page_numbers", "Page numbers", "select", options=("yes", "no"), default="yes"),
    )),
    Tool(
        "generate_document",
        "pdf",
        "Generate PPTX, DOCX, PDF",
        "Draft a PDF, DOCX, or PPTX from a request.",
        ".docx,.txt,.md",
        False,
        (
            _f("request", "Request", "textarea", required=True),
            _f("format", "Format", "select", options=("pdf", "docx", "pptx"), default="docx"),
            _f("template_preset", "Template", "text", default=""),
        ),
    ),
    Tool("image_compress", "image", "Compress image", "Re-save an image as JPEG or WebP at a lower quality.", "image/*", False, (
        _f("quality", "Quality (40-95)", "number", default="70"),
        _f("format", "Format", "select", options=("jpeg", "webp"), default="jpeg"),
    )),
    Tool("image_convert", "image", "Convert image", "Convert between JPEG, PNG, WebP, BMP, and GIF.", "image/*", False, (
        _f("format", "Format", "select", required=True, options=("jpeg", "png", "webp", "bmp", "gif"), default="png"),
    )),
    Tool("image_watermark", "image", "Watermark image", "Draw text on an image.", "image/*", False, (
        _f("text", "Watermark", "text", required=True, default="DRAFT"),
    )),
    Tool(
        "image_strip_exif",
        "image",
        "Remove Your Privacy",
        "Remove privacy information such as your GPS location and other metadata from your image.",
        "image/*",
        False,
    ),
    Tool(
        "image_remove_bg",
        "image",
        "Remove background",
        "Remove the background of your image.",
        "image/*",
        False,
    ),
    Tool(
        "favicon",
        "image",
        "Create Icon (Favicon)",
        "Create multi-size icon from your image.",
        "image/*",
        False,
    ),
    # YouTube MP4/MP3 moved to the on-device ytube-download app (see youtube_download).
    # Tool("youtube_mp4", "media", "YouTube to MP4", "Download a YouTube video as MP4.", "", False, (
    #     _f("url", "YouTube URL", "text", required=True),
    #     _f("quality", "Quality", "select", options=("360", "480", "720", "1080", "best"), default="720"),
    # )),
    # Tool("youtube_mp3", "media", "YouTube to MP3", "Download audio only from a YouTube video as MP3.", "", False, (
    #     _f("url", "YouTube URL", "text", required=True),
    #     _f("quality", "Quality", "select", options=("64", "128", "192", "320"), default="192"),
    # )),
    Tool(
        "video_translate",
        "media",
        "Video Translation",
        "Translate a video’s speech to another language. Extracts audio, transcribes, translates, and returns subtitles.",
        "video/*",
        False,
        (
            _f("source_language", "From language", "select", options=("auto", "en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="auto"),
            _f("language", "Target language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        ),
    ),
    Tool(
        "youtube_summarize",
        "media",
        "Summarize YouTube",
        "Summarize a YouTube video from its captions or audio transcript.",
        "",
        False,
        (
            _f("url", "YouTube URL", "text", required=True),
            _f("language", "Summary language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        ),
    ),
    Tool(
        "youtube_translate",
        "media",
        "Translate YouTube",
        "Translate a YouTube video’s speech or captions into another language.",
        "",
        False,
        (
            _f("url", "YouTube URL", "text", required=True),
            _f("source_language", "From language", "select", options=("auto", "en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="auto"),
            _f("language", "Target language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        ),
    ),
    Tool(
        "audio_translate",
        "media",
        "Audio Translation",
        "Translate uploaded audio into another language. Returns translated text and spoken MP3.",
        "audio/*",
        False,
        (
            _f("source_language", "From language", "select", options=("auto", "en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="auto"),
            _f("language", "Target language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        ),
    ),
    Tool(
        "tts",
        "media",
        "Text To Audio",
        "Translate text into your selected language audio in MP3 format (Up to 80,000 characters, about 30 pages).",
        "",
        False,
        (
            _f("text", "Text", "textarea", required=True),
            _f("language", "Output language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
        ),
    ),
    Tool(
        "stt",
        "media",
        "Audio to Text",
        "Transcribe an audio file into text.",
        "audio/*",
        False,
        (
            _f("language", "Language", "select", options=("auto", "en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="auto"),
        ),
    ),
    Tool(
        "extract_audio",
        "media",
        "Extract audio",
        "Extract audio track from a video and save as MP3 audio.",
        "video/*",
        False,
    ),
    Tool(
        "media_compress",
        "media",
        "Compress media",
        "Compress audio or video file into small size.",
        "audio/*,video/*",
        False,
        (
            _f("kind", "Kind", "select", options=("audio", "video"), default="video"),
        ),
    ),
    Tool(
        "media_trim",
        "media",
        "Trim media",
        "Cut a clip between start and end timestamps (seconds).",
        "audio/*,video/*",
        False,
        (
            _f("start", "Start seconds", "number", default="0"),
            _f("end", "End seconds", "number", required=True),
        ),
    ),
    Tool(
        "media_convert",
        "media",
        "Convert media",
        "Convert media types among MP3, MP4, WAV, M4A, WEBM.",
        "audio/*,video/*",
        False,
        (
            _f("format", "Format", "select", required=True, options=("mp3", "wav", "m4a", "mp4", "webm"), default="mp3"),
        ),
    ),
    Tool(
        "youtube_download",
        "media",
        "Download YouTube",
        "Download YouTube on your personal device. Server download is not supported.",
        "",
        False,
    ),
    Tool(
        "image_privacy_check",
        "safety",
        "Image Privacy Check",
        "Check privacy information such as your GPS location and other metadata in your image.",
        "image/*",
        False,
    ),
    Tool(
        "web_search",
        "search",
        "Search a Person or Product or Topic",
        "Enterprise people/product/topic search across web, news, social, and science via SearXNG, with regional ranking for realtime-ai.",
        "",
        False,
        (
            _f("query", "Name or topic", "text", required=True),
            _f("mode", "Mode", "select", options=("auto", "person", "topic"), default="auto"),
            _f("region_mode", "Region priority", "select", options=("auto", "manual"), default="auto"),
            _f("region", "Region code", "text", default="AUTO"),
            _f("location", "Region / location", "text", default=""),
            _f("language", "Language", "select", options=("en", "yue", "zh", "ta", "hi", "ml", "kn", "te"), default="en"),
            _f("interests", "Profile interests (comma-separated)", "text", default=""),
            _f("industry", "Profile industry", "text", default=""),
        ),
    ),
    Tool("qr_scan", "utility", "Scan QR Code", "Read a QR code with the camera or from an image.", "image/*", False),
    Tool("qr_generate", "utility", "Create QR Code", "Create a QR code PNG.", "", False, (
        _f("text", "QR code", "text", required=True),
    )),
    Tool("barcode_scan", "utility", "Scan Barcode", "Read a barcode with the camera or from an image.", "image/*", False),
    Tool("barcode_generate", "utility", "Create Barcode", "Create a Code128 barcode PNG.", "", False, (
        _f("text", "Barcode", "text", required=True),
    )),
    Tool("text_diff", "utility", "Text diff", "Compare two pieces of text.", "", False, (
        _f("left", "Original", "textarea", required=True),
        _f("right", "Changed", "textarea", required=True),
    )),
    Tool("case_convert", "utility", "Change case", "Convert text case.", "", False, (
        _f("style", "Style", "select", options=("upper", "lower", "title", "snake", "kebab", "camel"), default="lower"),
        _f("text", "Text", "textarea", required=True),
    )),
)

BY_ID = {item.id: item for item in TOOLS}

CATEGORIES = (
    ("search", "Search"),
    ("pdf", "Documents / PDF"),
    ("image", "Images"),
    ("media", "YouTube/Audio/Video"),
    ("utility", "Utilities"),
    ("ai", "AI"),
    ("safety", "Scam & Virus Check"),
)
