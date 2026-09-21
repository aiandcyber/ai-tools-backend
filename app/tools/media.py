import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx

from app import config

VOICES = {
    "en": "en-US-AriaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ta": "ta-IN-PallaviNeural",
    "hi": "hi-IN-SwaraNeural",
    "ml": "ml-IN-SobhanaNeural",
    "kn": "kn-IN-SapnaNeural",
    "te": "te-IN-ShrutiNeural",
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


def text_to_speech(text: str, language: str, dest: Path) -> Path:
    import edge_tts

    voice = VOICES.get(language, VOICES["en"])

    async def _save() -> None:
        await edge_tts.Communicate(text, voice).save(str(dest))

    asyncio.run(_save())
    return dest


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
