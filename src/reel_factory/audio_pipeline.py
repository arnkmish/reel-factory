"""
Audio generation pipeline: per-scene TTS narration.
Each scene gets its own TTS call so we know the exact duration,
which drives the video segment length for audio-video alignment.

Supports three TTS backends via config:
  - kokoro  (default, cheapest, $0.02/1k chars)
  - minimax (expressive, ~$0.015/call)
  - seed    (ByteDance Seed Speech, warm storyteller, $0.03/1k chars)

Audio duration is measured via ffprobe after download for accuracy —
API-reported durations are often 0 or unreliable.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from typing import List, Optional

from reel_factory.fal_gateway import FalGateway
from reel_factory.models import GeneratedAudioAsset, ScriptPackage, ScriptScene


def _measure_audio_duration(path: str) -> float:
    """Measure the real duration of an audio file using ffprobe.

    Falls back to 5.0s if ffprobe is unavailable or fails — this is
    a safe default that won't break assembly but signals the measurement
    wasn't possible.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            fmt = json.loads(result.stdout).get("format", {})
            return float(fmt.get("duration", 5.0))
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return 5.0


class AudioPipeline:
    """Generates per-scene audio assets (narration) for a reel."""

    def __init__(
        self,
        gateway: FalGateway,
        tts_endpoint: str = "fal-ai/kokoro/american-english",
        tts_backend: str = "kokoro",
        voice: str = "af_nova",
        speed: float = 0.85,
        workdir: Optional[str] = None,
    ):
        self.gateway = gateway
        self.tts_endpoint = tts_endpoint
        self.tts_backend = tts_backend
        self.voice = voice
        self.speed = speed
        self.workdir = workdir or os.path.join(os.getcwd(), "runtime", "output")

    def _generate_speech(self, text: str) -> dict:
        """Call the appropriate TTS backend based on configuration."""
        if self.tts_backend == "minimax":
            return self.gateway.generate_speech_minimax(
                text=text,
                voice=self.voice if self.voice != "af_nova" else "English_expressive_narrator",
                endpoint=self.tts_endpoint,
            )
        elif self.tts_backend == "seed":
            return self.gateway.generate_speech_seed(
                text=text,
                voice=self.voice if self.voice != "af_nova" else "stokie_en",
                speed=self.speed,
                endpoint=self.tts_endpoint,
            )
        else:  # kokoro (default)
            return self.gateway.generate_speech(
                text=text,
                voice=self.voice,
                speed=self.speed,
                endpoint=self.tts_endpoint,
            )

    def _extract_audio_url(self, result: dict) -> str:
        """Extract the audio URL from various fal response formats."""
        if "audio" in result:
            return result["audio"].get("url", "")
        elif "output" in result:
            if isinstance(result["output"], dict):
                return result["output"].get("url", "")
            elif isinstance(result["output"], str):
                return result["output"]
        return ""

    def _download_audio(self, url: str, scene_id: str) -> Optional[str]:
        """Download audio to local file, return path."""
        if not url:
            return None
        os.makedirs(self.workdir, exist_ok=True)
        # Use .wav for Kokoro, .mp3 for others — match what the API returns
        ext = ".wav" if "kokoro" in self.tts_endpoint else ".mp3"
        local_path = os.path.join(self.workdir, f"narration_{scene_id}{ext}")
        try:
            urllib.request.urlretrieve(url, local_path)
            return local_path
        except Exception:
            return None

    def generate_scene_narration(
        self,
        scene: ScriptScene,
    ) -> GeneratedAudioAsset:
        """Generate TTS narration for a single scene and download it locally."""
        narration_text = (scene.narration or "").strip()
        if not narration_text:
            narration_text = scene.screen_text

        result = self._generate_speech(narration_text)

        audio_url = self._extract_audio_url(result)

        # Try API-reported duration first, then measure with ffprobe
        duration_ms = result.get("duration_ms", 0)
        duration_s = duration_ms / 1000.0 if duration_ms else result.get("duration", 0.0)

        # Download locally
        local_path = self._download_audio(audio_url, scene.scene_id)

        # Measure real duration with ffprobe — always more accurate than API
        if local_path and os.path.exists(local_path):
            measured = _measure_audio_duration(local_path)
            if measured > 0:
                duration_s = measured

        return GeneratedAudioAsset(
            track_type="narration",
            scene_id=scene.scene_id,
            endpoint=self.tts_endpoint,
            model_version=self.tts_endpoint.split("/")[-1] if "/" in self.tts_endpoint else self.tts_endpoint,
            text=narration_text,
            request_id=result.get("request_id", ""),
            output_url=audio_url,
            local_path=local_path,
            cost=result.get("cost", 0.0),
            duration=duration_s,
        )

    def generate_all_narration(
        self,
        script: ScriptPackage,
    ) -> List[GeneratedAudioAsset]:
        """Generate per-scene narration for all scenes in the script.

        The final_moral is appended to the last scene's narration
        so we don't need a separate audio track for it.
        """
        audio_assets: List[GeneratedAudioAsset] = []

        for scene in script.scenes:
            audio = self.generate_scene_narration(scene)
            audio_assets.append(audio)

        # Report total duration for sanity checking
        total = self.get_total_duration(audio_assets)
        print(f"  Total narration duration: {total:.1f}s")
        if total < 15:
            print(f"  WARNING: Total audio is only {total:.1f}s — narration may be too brief")
        elif total > 45:
            print(f"  WARNING: Total audio is {total:.1f}s — narration may be too long")

        return audio_assets

    def get_total_duration(self, audio_assets: List[GeneratedAudioAsset]) -> float:
        """Return the total narration duration across all scenes."""
        return sum(a.duration for a in audio_assets)