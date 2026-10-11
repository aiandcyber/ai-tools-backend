---
name: media-tools
description: Audio/video convert, trim, compress, extract audio, YouTube download (MP4/MP3), text-to-speech, speech-to-text.
---

# Media tools

Use `run_media_tool` with the matching `tool_id`.

- `youtube_mp4` / `youtube_mp3` — paste a YouTube URL; no file upload.
- TTS: `language` is the MP3 output language. Other-language text is translated first, then spoken with edge-tts.
- STT needs OpenRouter configuration.
- FFmpeg must be available in the runtime for convert/trim/compress and YouTube MP3.
