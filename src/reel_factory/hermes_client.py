"""
Hermes client for bounded generation and review tasks.
Wraps Hermes CLI subprocess calls with structured JSON I/O.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from reel_factory.models import ReviewResult


class HermesClient:
    """Client for invoking Hermes for structured generation/review tasks."""

    def __init__(self, profile: str = "default", timeout: int = 120):
        self.profile = profile
        self.timeout = timeout

    def _call_hermes(self, prompt: str, schema: Optional[Dict] = None) -> str:
        """Invoke Hermes with a prompt and return raw output."""
        cmd = [
            "hermes", "chat", "-q", prompt,
            "-Q",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Hermes CLI error: {result.stderr[:500]}")
            output = result.stdout.strip()
            # Strip trailing "session_id: ..." line that Hermes adds in quiet mode
            lines = output.split("\n")
            if lines and lines[-1].startswith("session_id:"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Hermes timed out after {self.timeout}s")

    @staticmethod
    def _extract_json(raw: str) -> Dict[str, Any]:
        """Extract JSON from raw LLM output, handling markdown fences,
        box-drawing reasoning headers, and other common wrapping."""
        raw = raw.strip()

        # Strategy 1: Find a JSON code fence ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.DOTALL)
        if fence_match:
            return json.loads(fence_match.group(1).strip())

        # Strategy 2: Find the first { ... } block (greedy outermost)
        # This handles cases where there's text before/after the JSON
        start = raw.find("{")
        if start != -1:
            # Find matching closing brace by counting
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == "{":
                    depth += 1
                elif raw[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[start:i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
            # Try a simple substring
            try:
                return json.loads(raw[start:])
            except json.JSONDecodeError:
                pass

        # Strategy 3: Direct parse
        return json.loads(raw)

    def generate_structured(
        self, prompt: str, system_context: str = ""
    ) -> Dict[str, Any]:
        """Generate structured JSON output from Hermes."""
        full_prompt = f"{system_context}\n\n{prompt}\n\nRespond with valid JSON only. No markdown fences."
        raw = self._call_hermes(full_prompt)
        return self._extract_json(raw)

    def review_artifact(
        self,
        artifact_description: str,
        source_context: str,
        review_prompt_path: str | Path,
    ) -> ReviewResult:
        """Review an artifact using a prompt template."""
        prompt_text = Path(review_prompt_path).read_text()
        full_prompt = (
            f"Source context:\n{source_context}\n\n"
            f"Artifact to review:\n{artifact_description}\n\n"
            f"Review instructions:\n{prompt_text}\n\n"
            "Return a valid JSON object matching the ReviewResult schema."
        )
        raw = self._call_hermes(full_prompt)
        data = self._extract_json(raw)
        return ReviewResult(**data)