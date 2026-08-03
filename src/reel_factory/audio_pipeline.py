"""
Audio generation pipeline: per-scene TTS narration.
Each scene gets its own TTS call so we know the exact duration,
which drives the video clip length for audio-video alignment.
"""
from __future__ import annotations

import os
import urllib.request
from typing import List, Optional

from reel_factory.fal_gateway import FalGateway
from reel_factory.models import GeneratedAudioAsset, ScriptPackage, ScriptScene


class AudioPipeline:
    """Generates per-scene audio assets (narration) for a reel."""

    def __init__(
        self,
        gateway: FalGateway,
        tts_endpoint: str = "fal-ai/kokoro/american-english",
        workdir: Optional[str] = None,
    ):
        self.gateway = gateway
        self.tts_endpoint = tts_endpoint
        self.workdir = workdir or os.path.join(os.getcwd(), "runtime", "output")

    def generate_scene_narration(
        self,
        scene: ScriptScene,
    ) -> GeneratedAudioAsset:
        """Generate TTS narration for a single scene and download it locally."""
        narration_text = (scene.narration or "").strip()
        if not narration_text:
            narration_text = scene.screen_text

        result = self.gateway.generate_speech(
            text=narration_text,
            endpoint=self.tts_endpoint,
        )

        audio_url = ""
        if "audio" in result:
            audio_url = result["audio"].get("url", "")
        elif "output" in result:
            audio_url = result["output"].get("url", "")

        duration_ms = result.get("duration_ms", 0)
        duration_s = duration_ms / 1000.0 if duration_ms else result.get("duration", 0.0)

        # Download locally
        local_path = None
        if audio_url:
            os.makedirs(self.workdir, exist_ok=True)
            local_path = os.path.join(self.workdir, f"narration_{scene.scene_id}.wav")
            try:
                urllib.request.urlretrieve(audio_url, local_path)
            except Exception:
                local_path = None

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
        
        The final_moral is appended as part of the last scene's narration
        so we don't need a separate audio track for it.
        """
        audio_assets: List[GeneratedAudioAsset] = []
        
        for scene in script.scenes:
            audio = self.generate_scene_narration(scene)
            audio_assets.append(audio)
        
        return audio_assets

    def get_total_duration(self, audio_assets: List[GeneratedAudioAsset]) -> float:
        """Return the total narration duration across all scenes."""
        return sum(a.duration for a in audio_assets)