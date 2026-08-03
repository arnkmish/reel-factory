"""
Image generation pipeline: turns storyboard scenes into generated images.
Uses Qwen Image 2 via fal.ai for initial generation, and Qwen Image Edit 2511
for character-consistent sequential editing of subsequent scenes.

Character consistency strategy:
  - Scene 1: generate from scratch via qwen-image-2/text-to-image
  - Scenes 2+: edit the previous scene's image via qwen-image-edit-2511,
    which preserves character appearance (face, clothes, colors) while
    adapting to the new scene's pose, action, or background.
"""
from __future__ import annotations

import os
import urllib.request
from typing import List, Optional

from reel_factory.fal_gateway import FalGateway
from reel_factory.download import download_file
from reel_factory.models import (
    GeneratedImageAsset, StoryboardPackage, StoryboardScene,
)


class ImagePipeline:
    """Generates images from storyboard scenes with optional character consistency."""

    def __init__(
        self,
        gateway: FalGateway,
        endpoint: str = "fal-ai/qwen-image-2/text-to-image",
        edit_endpoint: str = "fal-ai/qwen-image-edit-2511",
        character_consistency: bool = True,
        workdir: Optional[str] = None,
    ):
        self.gateway = gateway
        self.endpoint = endpoint
        self.edit_endpoint = edit_endpoint
        self.character_consistency = character_consistency
        self.workdir = workdir or os.path.join(os.getcwd(), "runtime", "output")

    def _extract_image_url(self, result: dict) -> str:
        """Extract the image URL from various fal response formats."""
        if "images" in result and result["images"]:
            return result["images"][0].get("url", "")
        elif "image" in result:
            url = result["image"].get("url", "")
            if url:
                return url
            # Some edit endpoints return image as a string
            if isinstance(result["image"], str):
                return result["image"]
        return ""

    def _download_image(self, url: str, scene_id: str) -> Optional[str]:
        """Download image to local file, return path."""
        if not url:
            return None
        os.makedirs(self.workdir, exist_ok=True)
        local_path = os.path.join(self.workdir, f"image_{scene_id}.png")
        if download_file(url, local_path):
            return local_path
        return None

    def generate_scene(
        self,
        scene: StoryboardScene,
        attempt: int = 1,
        seed: Optional[int] = None,
        previous_image_url: Optional[str] = None,
    ) -> GeneratedImageAsset:
        """Generate a single image for a storyboard scene.

        If character_consistency is enabled and a previous_image_url is provided,
        uses image-to-image editing to preserve character appearance.
        Otherwise, generates from scratch.
        """
        use_edit = (
            self.character_consistency
            and previous_image_url is not None
        )

        if use_edit and previous_image_url is not None:
            result = self.gateway.edit_image(
                prompt=scene.image_prompt,
                image_url=previous_image_url,
                negative_prompt=scene.negative_prompt,
                seed=seed,
                endpoint=self.edit_endpoint,
            )
            endpoint_used = self.edit_endpoint
        else:
            result = self.gateway.generate_image(
                prompt=scene.image_prompt,
                negative_prompt=scene.negative_prompt,
                seed=seed,
                endpoint=self.endpoint,
            )
            endpoint_used = self.endpoint

        output_url = self._extract_image_url(result)
        local_path = self._download_image(output_url, scene.scene_id)

        return GeneratedImageAsset(
            scene_id=scene.scene_id,
            attempt=attempt,
            endpoint=endpoint_used,
            model_version=endpoint_used.split("/")[-1] if "/" in endpoint_used else endpoint_used,
            prompt=scene.image_prompt,
            negative_prompt=scene.negative_prompt,
            seed=seed or 0,
            request_id=result.get("request_id", ""),
            output_url=output_url,
            local_path=local_path,
            cost=result.get("cost", 0.0),
        )

    def generate_all(
        self,
        storyboard: StoryboardPackage,
        attempt: int = 1,
    ) -> List[GeneratedImageAsset]:
        """Generate images for all scenes in a storyboard.

        When character_consistency is enabled:
          - Scene 1 is generated from scratch
          - Scenes 2+ are generated via image-to-image editing on the
            previous scene's image, preserving character appearance
        """
        images = []
        previous_url: Optional[str] = None

        for i, scene in enumerate(storyboard.scenes):
            seed = 1000 + i  # deterministic seed per scene

            if self.character_consistency and i > 0 and previous_url:
                print(f"    Generating image for {scene.scene_id} (editing previous for consistency)...")
            else:
                print(f"    Generating image for {scene.scene_id} (from scratch)...")

            image = self.generate_scene(
                scene,
                attempt=attempt,
                seed=seed,
                previous_image_url=previous_url if i > 0 else None,
            )
            images.append(image)

            # Chain the output URL to the next scene for editing
            if image.output_url:
                previous_url = image.output_url

        return images