import asyncio
import logging
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import httpx

from app import config

_log = logging.getLogger("uvicorn.error")
_tts_lock = threading.Lock()

VOICES = {
    "en": "en-US-AriaNeural",
    "yue": "zh-HK-HiuMaanNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ta": "ta-IN-PallaviNeural",
    "hi": "hi-IN-SwaraNeural",
    "ml": "ml-IN-SobhanaNeural",
    "kn": "kn-IN-SapnaNeural",
    "te": "te-IN-ShrutiNeural",
}

# Microsoft often returns NoAudioReceived for a retired/busy voice; try others.
VOICE_CHAINS = {
    "en": (
        "en-US-AriaNeural",
        "en-US-JennyNeural",
        "en-US-EmmaMultilingualNeural",
    ),
    "yue": ("zh-HK-HiuMaanNeural", "zh-HK-HiuGaaiNeural", "zh-HK-WanLungNeural"),
    "zh": ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"),
    "ta": ("ta-IN-PallaviNeural", "ta-IN-ValluvarNeural", "en-US-EmmaMultilingualNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "en-US-EmmaMultilingualNeural"),
    "ml": ("ml-IN-SobhanaNeural", "en-US-EmmaMultilingualNeural"),
    "kn": ("kn-IN-SapnaNeural", "en-US-EmmaMultilingualNeural"),
    "te": ("te-IN-ShrutiNeural", "en-US-EmmaMultilingualNeural"),
}


def _ffmpeg(args: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed. The Fargate image includes it.")
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True, timeout=300)


def convert_media(src: Path, dest: Path) -> Path:
    _ffmpeg(["-i", str(src), str(dest)])
    return dest


def trim_media(src: Path, dest: Path, start: str, end: str) -> Path:
    _ffmpeg(["-i", str(src), "-ss", start or "0", "-to", end, str(dest)])
    return dest


def compress_media(src: Path, dest: Path, kind: str) -> Path:
    if kind == "audio":
        _ffmpeg(["-i", str(src), "-b:a", "96k", dest.with_suffix(".mp3")])
        return dest.with_suffix(".mp3")
    _ffmpeg(["-i", str(src), "-vcodec", "libx264", "-crf", "30", "-preset", "veryfast", dest.with_suffix(".mp4")])
    return dest.with_suffix(".mp4")


def extract_audio(src: Path, dest: Path) -> Path:
    _ffmpeg(["-i", str(src), "-vn", "-acodec", "libmp3lame", "-q:a", "4", str(dest)])
    return dest


_YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/",
    re.IGNORECASE,
)

MP4_QUALITIES = ("360", "480", "720", "1080", "best")
MP3_QUALITIES = ("64", "128", "192", "320")


def _youtube_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ValueError("Paste a YouTube URL")
    if not _YOUTUBE_RE.search(text):
        raise ValueError("URL must be a YouTube link")
    return text


def _youtube_downloaded_file(dest_dir: Path, suffix: str) -> Path:
    matches = sorted(dest_dir.glob(f"*{suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"Download finished but no {suffix} file was found")
    return matches[0]


_DOH_ENDPOINTS = (
    "https://1.1.1.1/dns-query",
    "https://dns.google/resolve",
)
_doh_cache: dict[str, list[str]] = {}
_doh_patched = False
_orig_getaddrinfo = socket.getaddrinfo


def _doh_lookup(hostname: str) -> list[str]:
    cached = _doh_cache.get(hostname)
    if cached is not None:
        return cached
    ips: list[str] = []
    for endpoint in _DOH_ENDPOINTS:
        try:
            response = httpx.get(
                endpoint,
                params={"name": hostname, "type": "A"},
                headers={"accept": "application/dns-json"},
                timeout=8,
            )
            if response.status_code >= 400:
                continue
            answers = response.json().get("Answer") or []
            ips = [item["data"] for item in answers if item.get("type") == 1 and item.get("data")]
            if ips:
                break
        except Exception:
            continue
    _doh_cache[hostname] = ips
    return ips


def _should_doh(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    return host in {
        "youtube.com",
        "youtu.be",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
        "speech.platform.bing.com",
    } or host.endswith(
        (
            ".youtube.com",
            ".googlevideo.com",
            ".ytimg.com",
            ".ggpht.com",
            ".google.com",
            ".bing.com",
            ".microsoft.com",
            ".office.net",
            ".trafficmanager.net",
        )
    )


def _getaddrinfo_with_doh(host, port, family=0, type=0, proto=0, flags=0):
    hostname = host.decode("ascii", "ignore") if isinstance(host, (bytes, bytearray)) else str(host)
    if not hostname or hostname[0].isdigit() or hostname.startswith("["):
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    ips = _doh_lookup(hostname)
    combined: list = []
    for ip in ips:
        combined.extend(_orig_getaddrinfo(ip, port, family, type, proto, flags))
    if combined:
        return combined
    raise socket.gaierror(socket.EAI_NONAME, f"Failed to resolve {hostname}")


def _ensure_doh_dns_fallback() -> None:
    """WSL/VPN often blocks UDP DNS (port 53) while HTTPS still works."""
    global _doh_patched
    if _doh_patched:
        return
    socket.getaddrinfo = _getaddrinfo_with_doh  # type: ignore[assignment]
    _doh_patched = True


def _ydl_common() -> dict:
    _ensure_doh_dns_fallback()
    return {
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "restrictfilenames": True,
        "overwrites": True,
        "socket_timeout": 30,
        "force_ipv4": True,
    }


def _mp4_format(quality: str) -> str:
    raw = (quality or "720").strip().lower().replace("p", "")
    if raw == "best":
        return "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
    try:
        height = int(raw)
    except ValueError:
        height = 720
    return (
        f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={height}]+ba/"
        f"b[height<={height}]/"
        f"bv*+ba/b"
    )


def _mp3_bitrate(quality: str) -> str:
    raw = (quality or "192").strip().lower().replace("kbps", "").replace("k", "")
    if raw not in MP3_QUALITIES:
        raw = "192"
    return raw


def _fmt_bytes(fmt: dict) -> int:
    return int(fmt.get("filesize") or fmt.get("filesize_approx") or 0)


def _estimate_from_tbr(fmt: dict, duration: float) -> int:
    tbr = fmt.get("tbr") or fmt.get("abr") or 0
    if not tbr or not duration:
        return 0
    return int(float(tbr) * 1000 / 8 * float(duration))


def _is_video(fmt: dict) -> bool:
    vcodec = fmt.get("vcodec")
    return bool(vcodec and vcodec != "none")


def _is_audio_only(fmt: dict) -> bool:
    acodec = fmt.get("acodec")
    vcodec = fmt.get("vcodec")
    return bool(acodec and acodec != "none" and (not vcodec or vcodec == "none"))


def _is_progressive(fmt: dict) -> bool:
    acodec = fmt.get("acodec")
    vcodec = fmt.get("vcodec")
    return bool(vcodec and vcodec != "none" and acodec and acodec != "none")


def _pick_best(candidates: list[dict], key) -> dict | None:
    if not candidates:
        return None
    return max(candidates, key=key)


def _video_for_height(formats: list[dict], max_height: int | None) -> dict | None:
    pool = []
    for fmt in formats:
        if not _is_video(fmt):
            continue
        height = int(fmt.get("height") or 0)
        if max_height is not None:
            if height <= 0 or height > max_height:
                continue
        pool.append(fmt)
    return _pick_best(
        pool,
        lambda f: (
            int(f.get("height") or 0),
            1 if (f.get("ext") or "") == "mp4" else 0,
            float(f.get("tbr") or 0),
            _fmt_bytes(f),
        ),
    )


def _audio_track(formats: list[dict]) -> dict | None:
    pool = [fmt for fmt in formats if _is_audio_only(fmt)]
    return _pick_best(
        pool,
        lambda f: (
            1 if (f.get("ext") or "") in ("m4a", "mp4") else 0,
            float(f.get("abr") or f.get("tbr") or 0),
            _fmt_bytes(f),
        ),
    )


def _progressive_for_height(formats: list[dict], max_height: int | None) -> dict | None:
    pool = []
    for fmt in formats:
        if not _is_progressive(fmt):
            continue
        height = int(fmt.get("height") or 0)
        if max_height is not None:
            if height <= 0 or height > max_height:
                continue
        pool.append(fmt)
    return _pick_best(
        pool,
        lambda f: (
            int(f.get("height") or 0),
            1 if (f.get("ext") or "") == "mp4" else 0,
            float(f.get("tbr") or 0),
            _fmt_bytes(f),
        ),
    )


def _mp4_expected_bytes(formats: list[dict], quality: str, duration: float) -> int | None:
    raw = (quality or "720").strip().lower().replace("p", "")
    max_height = None if raw == "best" else int(raw) if raw.isdigit() else 720
    progressive = _progressive_for_height(formats, max_height)
    video = _video_for_height(formats, max_height)
    audio = _audio_track(formats)
    size = 0
    if progressive:
        size = _fmt_bytes(progressive) or _estimate_from_tbr(progressive, duration)
    if video:
        vsize = _fmt_bytes(video) or _estimate_from_tbr(video, duration)
        asize = (_fmt_bytes(audio) or _estimate_from_tbr(audio, duration)) if audio else 0
        combined = vsize + asize
        if combined > size:
            size = combined
    return size or None


def youtube_probe(url: str, kind: str) -> dict:
    import yt_dlp

    kind = "mp3" if kind == "mp3" else "mp4"
    opts = {**_ydl_common(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(_youtube_url(url), download=False)
    duration = float(info.get("duration") or 0)
    formats = info.get("formats") or []
    qualities: list[dict] = []
    if kind == "mp4":
        for item in MP4_QUALITIES:
            size = _mp4_expected_bytes(formats, item, duration)
            qualities.append({
                "id": item,
                "label": "Best available" if item == "best" else f"{item}p",
                "bytes": size,
            })
    else:
        for item in MP3_QUALITIES:
            size = int(duration * int(item) * 1000 / 8) if duration else None
            qualities.append({
                "id": item,
                "label": f"{item} kbps",
                "bytes": size,
            })
    return {
        "title": info.get("title") or "",
        "duration": int(duration),
        "kind": kind,
        "qualities": qualities,
    }


def download_youtube_mp4(url: str, dest_dir: Path, quality: str = "720") -> Path:
    import yt_dlp

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        **_ydl_common(),
        "format": _mp4_format(quality),
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(title).80s [%(id)s].%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(_youtube_url(url), download=True)
    return _youtube_downloaded_file(dest_dir, ".mp4")


def download_youtube_mp3(url: str, dest_dir: Path, quality: str = "192") -> Path:
    import yt_dlp

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed. MP3 conversion needs ffmpeg.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    bitrate = _mp3_bitrate(quality)
    opts = {
        **_ydl_common(),
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "%(title).80s [%(id)s].%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(_youtube_url(url), download=True)
    return _youtube_downloaded_file(dest_dir, ".mp3")


def text_to_speech(text: str, language: str, dest: Path) -> Path:
    """Sync TTS for tool runner. Safe when no event loop is running."""

    async def _save() -> None:
        await _edge_tts_save(text, language, dest)

    def _run() -> None:
        with _tts_lock:
            asyncio.run(_save())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _run()
    else:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_run).result(timeout=900)
    return dest


async def text_to_speech_async(text: str, language: str, dest: Path) -> Path:
    """Async TTS for /api/tts (agent speak replies)."""
    await _edge_tts_save(text, language, dest)
    return dest


# Microsoft Edge TTS drops long websocket payloads ("No audio was received").
# edge-tts itself also splits at 4096 *bytes* after XML escaping — stay under that.
TTS_CHUNK_CHARS = 800
TTS_CHUNK_BYTES = 3000
TTS_MAX_CHARS = 80_000


def _prefix_within_limits(text: str) -> str:
    hi = min(len(text), TTS_CHUNK_CHARS)
    while hi > 0 and len(text[:hi].encode("utf-8")) > TTS_CHUNK_BYTES:
        hi -= 1
    return text[:hi]


def _split_tts_chunks(text: str) -> list[str]:
    if len(text.encode("utf-8")) <= TTS_CHUNK_BYTES and len(text) <= TTS_CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        window = _prefix_within_limits(remaining)
        if not window:
            window = remaining[:1]
        if window == remaining:
            parts.append(remaining.strip())
            break
        cut = max(
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind(". "),
            window.rfind("? "),
            window.rfind("! "),
            window.rfind("。"),
            window.rfind("！"),
            window.rfind("？"),
            window.rfind(" "),
        )
        if cut < max(1, len(window) // 5):
            cut = len(window)
        piece = remaining[:cut].strip()
        if piece:
            parts.append(piece)
        remaining = remaining[cut:].lstrip()
    return [item for item in parts if item]


def _detect_tts_lang(text: str, declared: str) -> str:
    lang = (declared or "en").strip().lower() or "en"
    if lang in {"yue", "zh-hk", "zh_hk"}:
        lang = "yue"
    elif lang.startswith("zh"):
        lang = "zh"
    sample = text[:4000]
    counts = {
        "ta": sum(1 for ch in sample if "\u0b80" <= ch <= "\u0bff"),
        "hi": sum(1 for ch in sample if "\u0900" <= ch <= "\u097f"),
        "ml": sum(1 for ch in sample if "\u0d00" <= ch <= "\u0d7f"),
        "kn": sum(1 for ch in sample if "\u0c80" <= ch <= "\u0cff"),
        "te": sum(1 for ch in sample if "\u0c00" <= ch <= "\u0c7f"),
        "zh": sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff"),
    }
    best_lang, best_n = max(counts.items(), key=lambda item: item[1])
    if best_n >= 20 and best_n / max(len(sample), 1) >= 0.12:
        if lang == "en" or lang not in VOICE_CHAINS:
            return best_lang
    return lang if lang in VOICE_CHAINS else "en"


def _concat_mp3(parts: list[Path], dest: Path) -> None:
    if len(parts) == 1:
        if parts[0] != dest:
            dest.write_bytes(parts[0].read_bytes())
        return
    listing = dest.parent / f"{dest.stem}-concat.txt"
    lines = []
    for path in parts:
        escaped = str(path).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(dest),
        ]
    )


async def _edge_tts_one(text: str, voices: list[str], dest: Path, *, chunk_label: str) -> None:
    import edge_tts

    last_error: Exception | None = None
    for voice in voices:
        for attempt in range(3):
            try:
                if dest.exists():
                    dest.unlink()
                await edge_tts.Communicate(text, voice, receive_timeout=45).save(str(dest))
                if dest.exists() and dest.stat().st_size > 0:
                    return
                last_error = RuntimeError(
                    "No audio was received. Please verify that your parameters are correct."
                )
            except Exception as exc:
                last_error = exc
            _log.warning(
                "edge-tts %s voice=%s attempt=%s failed: %s",
                chunk_label,
                voice,
                attempt + 1,
                last_error,
            )
            await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError(
        f"{chunk_label} failed ({len(text)} chars): {last_error}"
        if last_error
        else f"{chunk_label} failed"
    )


async def _edge_tts_save(text: str, language: str, dest: Path) -> None:
    _ensure_doh_dns_fallback()
    spoken = (text or "").strip()
    if not spoken:
        raise ValueError("Enter text to speak")
    if len(spoken) > TTS_MAX_CHARS:
        raise ValueError(
            f"Text is {len(spoken):,} characters. Maximum is {TTS_MAX_CHARS:,}. "
            "Split the text and run Text to speech more than once."
        )
    lang = _detect_tts_lang(spoken, language)
    voices = list(VOICE_CHAINS.get(lang, VOICE_CHAINS["en"]))
    chunks = _split_tts_chunks(spoken)
    _log.info(
        "tts start chars=%s bytes=%s declared=%s lang=%s chunks=%s voice0=%s",
        len(spoken),
        len(spoken.encode("utf-8")),
        language,
        lang,
        len(chunks),
        voices[0],
    )
    if len(chunks) == 1:
        await _edge_tts_one(chunks[0], voices, dest, chunk_label="chunk 1/1")
        return
    parts: list[Path] = []
    for index, chunk in enumerate(chunks):
        part = dest.parent / f"{dest.stem}-{index:03d}.mp3"
        await _edge_tts_one(
            chunk,
            voices,
            part,
            chunk_label=f"chunk {index + 1}/{len(chunks)}",
        )
        parts.append(part)
    _concat_mp3(parts, dest)


def speech_to_text(src: Path) -> str:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    with src.open("rb") as handle:
        response = httpx.post(
            f"{config.OPENROUTER_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
            files={"file": (src.name, handle)},
            data={"model": config.OPENROUTER_STT_MODEL},
            timeout=180,
        )
    if response.status_code >= 400:
        raise RuntimeError(response.text[:800])
    payload = response.json()
    return payload.get("text") or str(payload)
