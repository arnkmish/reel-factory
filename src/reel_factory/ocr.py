"""
OCR verification for rendered text overlays.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


class OCRPipeline:
    """Verifies text fidelity in rendered video frames."""

    def __init__(self, tesseract_cmd: str = "tesseract"):
        self.tesseract_cmd = tesseract_cmd

    def extract_text(self, image_path: str | Path) -> str:
        """Extract text from an image using Tesseract OCR."""
        try:
            import subprocess
            result = subprocess.run(
                [self.tesseract_cmd, str(image_path), "stdout"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def verify_text(
        self,
        image_path: str | Path,
        expected_text: str,
    ) -> Tuple[bool, str, float]:
        """
        Verify that the expected text appears in the rendered image.
        Returns (match, extracted_text, confidence).
        """
        extracted = self.extract_text(image_path)
        if not extracted:
            return False, "", 0.0

        # Simple substring match for v1
        match = expected_text.lower() in extracted.lower()
        confidence = 1.0 if match else 0.0
        return match, extracted, confidence
