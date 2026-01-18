from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1").rstrip("/")
API_KEY = os.getenv("ELEVENLABS_API_KEY")

TTS_ENDPOINT = os.getenv("ELEVENLABS_TTS_ENDPOINT", "/text-to-speech/{voice_id}")
STS_ENDPOINT = os.getenv("ELEVENLABS_STS_ENDPOINT", "/speech-to-speech/{voice_id}")
STT_ENDPOINT = os.getenv("ELEVENLABS_STT_ENDPOINT", "/speech-to-text")
SFX_ENDPOINT = os.getenv("ELEVENLABS_SFX_ENDPOINT", "/sound-generation")
ISOLATE_ENDPOINT = os.getenv("ELEVENLABS_ISOLATE_ENDPOINT", "/audio-isolation")
MUSIC_ENDPOINT = os.getenv("ELEVENLABS_MUSIC_ENDPOINT", "/music-generation")
VOICES_ENDPOINT = os.getenv("ELEVENLABS_VOICES_ENDPOINT", "/voices")
VOICE_GEN_ENDPOINT = os.getenv("ELEVENLABS_VOICE_GEN_ENDPOINT", "/text-to-voice/create")


def _headers(accept: str = "application/json") -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")
    return {
        "Accept": accept,
        "Content-Type": "application/json",
        "xi-api-key": API_KEY,
    }


def _audio_headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")
    return {
        "Accept": "audio/mpeg",
        "xi-api-key": API_KEY,
    }


def _raise_for_error(response: requests.Response, label: str) -> None:
    if response.ok:
        return
    text = response.text.strip()
    if len(text) > 800:
        text = text[:800] + "..."
    raise RuntimeError(f"{label} failed ({response.status_code}): {text}")


def list_voices() -> dict[str, Any]:
    url = f"{BASE_URL}{VOICES_ENDPOINT}"
    response = requests.get(url, headers=_headers(), timeout=60)
    _raise_for_error(response, "ElevenLabs voices")
    return response.json()


def text_to_speech(
    text: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    output_format: str = "mp3_44100_128",
    voice_settings: dict[str, Any] | None = None,
) -> bytes:
    url = f"{BASE_URL}{TTS_ENDPOINT.format(voice_id=voice_id)}"
    payload: dict[str, Any] = {
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
    }
    if voice_settings:
        sanitized = {k: v for k, v in voice_settings.items() if k != "speed"}
        if sanitized:
            payload["voice_settings"] = sanitized
    response = requests.post(url, json=payload, headers=_audio_headers(), timeout=120)
    _raise_for_error(response, "ElevenLabs TTS")
    return response.content


def speech_to_speech(
    audio_path: Path,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    voice_settings: dict[str, Any] | None = None,
) -> bytes:
    url = f"{BASE_URL}{STS_ENDPOINT.format(voice_id=voice_id)}"
    data: dict[str, Any] = {"model_id": model_id}
    if voice_settings:
        data["voice_settings"] = voice_settings
    with audio_path.open("rb") as handle:
        files = {"audio": handle}
        response = requests.post(
            url, data=data, files=files, headers=_audio_headers(), timeout=180
        )
        _raise_for_error(response, "ElevenLabs STS")
        return response.content


def speech_to_text(audio_path: Path, language: str | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{STT_ENDPOINT}"
    data: dict[str, Any] = {}
    if language:
        data["language_code"] = language
    with audio_path.open("rb") as handle:
        files = {"audio": handle}
        response = requests.post(
            url, data=data, files=files, headers=_headers(), timeout=180
        )
        _raise_for_error(response, "ElevenLabs STT")
        return response.json()


def sound_effects(prompt: str, duration_s: float = 2.5) -> bytes:
    url = f"{BASE_URL}{SFX_ENDPOINT}"
    payload = {"text": prompt, "duration_seconds": duration_s}
    response = requests.post(url, json=payload, headers=_audio_headers(), timeout=180)
    _raise_for_error(response, "ElevenLabs SFX")
    return response.content


def audio_isolation(audio_path: Path) -> bytes:
    url = f"{BASE_URL}{ISOLATE_ENDPOINT}"
    with audio_path.open("rb") as handle:
        files = {"audio": handle}
        response = requests.post(
            url, files=files, headers=_audio_headers(), timeout=180
        )
        _raise_for_error(response, "ElevenLabs isolation")
        return response.content


def music_generation(prompt: str, duration_s: float = 10.0) -> bytes:
    url = f"{BASE_URL}{MUSIC_ENDPOINT}"
    payload = {"text": prompt, "duration_seconds": duration_s}
    response = requests.post(url, json=payload, headers=_audio_headers(), timeout=180)
    if response.status_code == 404:
        # Fallback: use sound generation if music endpoint is unavailable.
        return sound_effects(f"music: {prompt}", duration_s=duration_s)
    _raise_for_error(response, "ElevenLabs music")
    return response.content


def voice_generation(name: str, description: str) -> dict[str, Any]:
    url = f"{BASE_URL}{VOICE_GEN_ENDPOINT}"
    payload = {"name": name, "text": description}
    response = requests.post(url, json=payload, headers=_headers(), timeout=180)
    _raise_for_error(response, "ElevenLabs voice generation")
    return response.json()
