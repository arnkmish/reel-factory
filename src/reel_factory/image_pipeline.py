"""
Image generation pipeline: turns storyboard scenes into generated images.
Uses Qwen Image 2 via fal.ai — supports negative_prompt + enable_prompt_expansion.
"""
from __future__ import annotations

from typing import List, Optional

from reel_factory.fal_gateway import FalGateway
from reel_factory.models import (
    GeneratedImageAsset, StoryboardPackage, StoryboardScene,
)


class ImagePipeline:
    """Generates images from storyboard scenes."""

    def __init__(self, gateway: FalGateway, endpoint: str = "fal-ai/qwen-image-2/text-to-image"):
        self.gateway = gateway
        self.endpoint = endpoint

    def generate_scene(
        self,
        scene: StoryboardScene,
        attempt: int = 1,
        seed: Optional[int] = None,
    ) -> GeneratedImageAsset:
        """Generate a single image for a storyboard scene."""
        result = self.gateway.generate_image(
            prompt=scene.image_prompt,
            negative_prompt=scene.negative_prompt,
            seed=seed,
            endpoint=self.endpoint,
        )

        # Extract output URL from fal response
        output_url = ""
        if "images" in result and result["images"]:
            output_url = result["images"][0].get("url", "")
        elif "image" in result:
            output_url = result["image"].get("url", "")

        return GeneratedImageAsset(
            scene_id=scene.scene_id,
            attempt=attempt,
            endpoint=self.endpoint,
            model_version=self.endpoint.split("/")[-1] if "/" in self.endpoint else self.endpoint,
            prompt=scene.image_prompt,
            negative_prompt=scene.negative_prompt,
            seed=seed or 0,
            request_id=result.get("request_id", ""),
            output_url=output_url,
            cost=result.get("cost", 0.0),
        )

    def generate_all(
        self,
        storyboard: StoryboardPackage,
        attempt: int = 1,
    ) -> List[GeneratedImageAsset]:
        """Generate images for all scenes in a storyboard."""
        images = []
        for i, scene in enumerate(storyboard.scenes):
            seed = 1000 + i  # deterministic seed per scene
            image = self.generate_scene(scene, attempt=attempt, seed=seed)
            images.append(image)
        return images