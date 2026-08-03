"""
fal.ai API gateway for image and speech generation.
No video generation — v2 uses static frames + FFmpeg.
Calculates cost per call based on published fal.ai pricing.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import fal_client

# ── Pricing (from fal.ai/pricing, per call) ──────────────────
# Qwen Image 2: $0.02 per megapixel
QWEN_IMAGE_PRICE_PER_MP = 0.02
# MiniMax Speech 2.8 HD: ~$0.015 per short clip (estimated, ~10-15s)
MINIMAX_SPEECH_PRICE_PER_CALL = 0.015
# Kokoro TTS American English: $0.02 per 1,000 characters (~$0.0016 for 80-char clip)
KOKORO_TTS_PRICE_PER_CHAR = 0.00002
# ElevenLabs Eleven V3: ~$0.30 per 1,000 characters (premium expressive voices)
ELEVEN_V3_TTS_PRICE_PER_CHAR = 0.0003


class FalGateway:
    """Gateway to fal.ai API endpoints."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FAL_KEY")
        if not self.api_key:
            # Try reading from .env file
            env_path = os.path.join(os.getcwd(), ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("FAL_KEY="):
                            self.api_key = line.split("=", 1)[1].strip()
                            break

    def _client(self):
        # Pass key explicitly to avoid stale cached auth tokens
        return fal_client.SyncClient(key=self.api_key)

    @staticmethod
    def _calc_image_cost(width: int, height: int) -> float:
        """Calculate image generation cost based on resolution."""
        megapixels = (width * height) / 1_000_000
        return round(megapixels * QWEN_IMAGE_PRICE_PER_MP, 4)

    def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        width: int = 1080,
        height: int = 1920,
        endpoint: str = "fal-ai/qwen-image-2/text-to-image",
    ) -> Dict[str, Any]:
        """Generate an image using the specified fal endpoint.

        Qwen Image 2 uses image_size {width, height} and supports
        negative_prompt + enable_prompt_expansion.
        """
        arguments: Dict[str, Any] = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "enable_prompt_expansion": True,
            "enable_safety_checker": True,
            "num_images": 1,
            "output_format": "png",
        }
        if negative_prompt:
            arguments["negative_prompt"] = negative_prompt
        if seed is not None:
            arguments["seed"] = seed

        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=180
        )
        # Populate cost since fal doesn't return it
        result["cost"] = self._calc_image_cost(width, height)
        return result

    # ── Qwen Image Edit 2511 (character consistency via image-to-image) ──
    def edit_image(
        self,
        prompt: str,
        image_url: str,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        width: int = 1080,
        height: int = 1920,
        endpoint: str = "fal-ai/qwen-image-edit-2511",
    ) -> Dict[str, Any]:
        """Edit an existing image while preserving visual identity.

        Uses `qwen-image-edit-2511` which accepts a reference image and
        a prompt describing the desired edit. The model preserves the
        subject's appearance (face, clothes, colors) while changing
        pose, scene, or expression — ideal for sequential scene
        generation with consistent characters.

        Parameters:
            prompt: The editing instruction (e.g. "Change pose to running")
            image_url: URL of the reference image to edit
            seed: Optional seed for reproducibility
            width, height: Target resolution (default 1080×1920)
        """
        arguments: Dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [image_url],
            "num_images": 1,
            "output_format": "png",
            "num_inference_steps": 28,
        }
        if negative_prompt:
            arguments["negative_prompt"] = negative_prompt
        if seed is not None:
            arguments["seed"] = seed

        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=180
        )
        # Edit costs $0.03 per megapixel — same pricing as generation
        result["cost"] = self._calc_image_cost(width, height)
        return result

    def generate_speech(
        self,
        text: str,
        voice: str = "af_nova",
        speed: float = 0.85,
        endpoint: str = "fal-ai/kokoro/american-english",
    ) -> Dict[str, Any]:
        """Generate speech audio from text using Kokoro TTS (American English).

        Defaults to af_nova (clear, natural storyteller — great for kids).
        Speed defaults to 0.85 for slow, clear, kid-friendly narration.
        Available Kokoro American English voices:
          Female: af_bella, af_nicole, af_sarah, af_sky, af_jessica, af_ally,
                  af_sharon, af_kore, af_aoede, af_nova
          Male:   am_adam, am_michael, am_eric, am_river, am_puck, am_echo,
                  am_onyx, am_santa, am_gurney
        """
        arguments = {
            "prompt": text,
            "voice": voice,
            "speed": speed,
        }
        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=300
        )
        # Populate cost since fal doesn't return it
        char_count = len(text)
        result["cost"] = round(char_count * KOKORO_TTS_PRICE_PER_CHAR, 6)
        return result

    def generate_speech_eleven_v3(
        self,
        text: str,
        voice: str = "Rachel",
        stability: float = 0.5,
        language_code: str = "en",
        endpoint: str = "fal-ai/elevenlabs/tts/eleven-v3",
    ) -> Dict[str, Any]:
        """Generate speech audio using ElevenLabs Eleven V3 via fal.ai.

        Eleven V3 is ElevenLabs' most expressive model — supports voice
        cloning, emotion control, and 29+ languages.  Uses natural
        voice names (Rachel, Aria, etc.) rather than voice IDs.

        Parameters:
            text: The text to convert to speech.
            voice: ElevenLabs voice name (default "Rachel").
                   Other popular voices: Aria, Domi, Belle, Michael, Elliott.
            stability: Voice stability 0-1 (default 0.5).  Lower = more
                       expressive/emotional, higher = more consistent.
            language_code: ISO 639-1 language code (default "en").
            endpoint: fal.ai endpoint (default eleven-v3).
        """
        arguments = {
            "text": text,
            "voice": voice,
            "stability": stability,
            "apply_text_normalization": "auto",
        }
        if language_code:
            arguments["language_code"] = language_code
        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=300
        )
        char_count = len(text)
        result["cost"] = round(char_count * ELEVEN_V3_TTS_PRICE_PER_CHAR, 6)
        return result

    # Kept for backward compatibility; not used by default
    def generate_speech_minimax(
        self,
        text: str,
        voice: str = "English_expressive_narrator",
        endpoint: str = "fal-ai/minimax/speech-2.8-hd",
    ) -> Dict[str, Any]:
        """Generate speech audio using MiniMax Speech 2.8 HD (legacy).

        Uses English_expressive_narrator voice with neutral emotion for a
        calm, professional narration tone.
        """
        arguments = {
            "prompt": text,
            "output_format": "url",
            "language_boost": "English",
            "voice_setting": {
                "voice_id": voice,
                "emotion": "neutral",
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
                "english_normalization": True,
            },
            "audio_setting": {
                "sample_rate": 44100,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=120
        )
        result["cost"] = MINIMAX_SPEECH_PRICE_PER_CALL
        return result

    def generate_speech_elevenlabs(
        self,
        text: str,
        voice: str = "Rachel",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        endpoint: str = "fal-ai/elevenlabs/tts/eleven-v3",
    ) -> Dict[str, Any]:
        """Generate speech audio using ElevenLabs TTS v3.

        High-quality expressive narration. Returns MP3 audio.
        Available voices include: Rachel, Domi, Antoni, Elli, Josh, Arnold,
        Adam, Sam, Bella, Daniel, Lilly, Michael, Charlotte, Matilda, Matthew,
        and many more from ElevenLabs voice library.

        Parameters:
            text: The text to synthesize
            voice: Voice ID or name (default: Rachel — warm narrator)
            stability: 0.0-1.0, higher = more consistent
            similarity_boost: 0.0-1.0, higher = closer to original voice
        """
        arguments = {
            "text": text,
            "voice_settings": {
                "voice_id": voice,
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }
        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=300
        )
        # ElevenLabs pricing: ~$0.30 per 1k chars on v3
        char_count = len(text)
        result["cost"] = round(char_count * 0.0003, 6)
        return result

    def generate_speech_seed(
        self,
        text: str,
        voice: str = "stokie_en",
        speed: float = 0.88,
        endpoint: str = "fal-ai/bytedance/seed-speech/tts/v2",
    ) -> Dict[str, Any]:
        """Generate speech audio using ByteDance Seed Speech TTS.

        Defaults to a warm storyteller persona using natural voice controls:
          - stokie_en voice (clear English)
          - speed=0.88 for gentle, unhurried pacing
          - voice_instruction steers tone without audio artifacts

        The voice_instruction is a natural-language prompt (not spoken) that
        tells the model HOW to deliver the text — e.g. slower, deeper, warmer.
        This avoids pitch-shift artifacts that can make TTS sound robotic.

        Valid English voices:
          - stokie_en  — clear English (default)
          - dacey_en   — warm English storyteller
          - tim_en     — steady English narrator
        """
        arguments = {
            "text": text,
            "voice": voice,
            "speed": speed,
            "voice_instruction": (
                "Speak slowly and warmly like a wise old grandfather "
                "telling bedtime stories to children. Gentle, steady pace "
                "with a deep, reassuring tone."
            ),
            "output_format": "mp3",
        }
        result = self._client().subscribe(
            endpoint, arguments=arguments, client_timeout=120
        )
        char_count = len(text)
        result["cost"] = round(char_count * 0.00003, 6)
        return result