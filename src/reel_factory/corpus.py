"""
Corpus management: loading, filtering, and selecting approved content items.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from reel_factory.models import CorpusItem, RiskTier


class Corpus:
    """Manages the approved content corpus."""

    def __init__(self, corpus_dir: str | Path):
        self.corpus_dir = Path(corpus_dir)
        self._items: List[CorpusItem] = []
        self._loaded = False

    def load(self) -> None:
        """Load all corpus items from the manifests directory."""
        manifest_dir = self.corpus_dir / "manifests"
        if not manifest_dir.exists():
            manifest_dir.mkdir(parents=True, exist_ok=True)
            self._items = []
            self._loaded = True
            return

        self._items = []
        for json_file in sorted(manifest_dir.glob("*.json")):
            with open(json_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item_data in data:
                        self._items.append(CorpusItem(**item_data))
                else:
                    self._items.append(CorpusItem(**data))
        self._loaded = True

    @property
    def items(self) -> List[CorpusItem]:
        if not self._loaded:
            self.load()
        return self._items

    def get_eligible(self, language: str = "English") -> List[CorpusItem]:
        """Return items that are approved and usable for production."""
        return [
            item for item in self.items
            if not item.sensitivity_flags
            and item.license
            and item.source_url
        ]

    def get_by_tradition(self, tradition: str) -> List[CorpusItem]:
        return [item for item in self.items if item.tradition.lower() == tradition.lower()]

    def get_by_risk_tier(self, tier: RiskTier) -> List[CorpusItem]:
        return [item for item in self.items if item.risk_tier == tier]

    def count(self) -> int:
        return len(self.items)
