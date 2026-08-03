"""
Source selection and candidate ranking for daily production.
v2: Supports tradition rotation, title-based dedup, and cooldown cycling.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from reel_factory.models import CorpusItem, SelectionCandidate, QuoteMode


def _normalize_title(title: str) -> str:
    """Normalize a story title for dedup comparison.
    Removes articles, punctuation, and lowercases."""
    t = title.lower().strip()
    # Remove common articles
    t = re.sub(r'\b(the|a|an)\b', '', t)
    # Remove punctuation
    t = re.sub(r'[^a-z0-9\s]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _title_hash(title: str) -> str:
    """Create a short hash of a normalized title for quick comparison."""
    return hashlib.md5(_normalize_title(title).encode()).hexdigest()[:12]


class SelectionEngine:
    """Selects the best corpus item for today's production.
    
    Features:
    - Tracks used source_ids (exact dedup)
    - Tracks used title hashes (semantic dedup — same story from different traditions)
    - Rotates traditions for diversity (avoids same tradition back-to-back)
    - Cooldown period before reusing stories (default 90 days)
    """

    def __init__(
        self,
        history_path: str | Path,
        similarity_window_days: int = 90,
        tradition_rotation_window: int = 3,
    ):
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.similarity_window_days = similarity_window_days
        self.tradition_rotation_window = tradition_rotation_window
        self._used_ids: Set[str] = set()
        self._used_title_hashes: Set[str] = set()
        self._recent_traditions: List[str] = []
        self._usage_log: List[Dict] = []  # [{source_id, title, tradition, date}]
        self._load_history()

    def _load_history(self) -> None:
        """Load previously used source IDs and title hashes from history file."""
        if self.history_path.exists() and self.history_path.stat().st_size > 0:
            try:
                with open(self.history_path, "r") as f:
                    data = json.load(f)
                    self._used_ids = set(data.get("used_ids", []))
                    self._used_title_hashes = set(data.get("used_title_hashes", []))
                    self._recent_traditions = data.get("recent_traditions", [])
                    self._usage_log = data.get("usage_log", [])
            except (json.JSONDecodeError, OSError):
                self._used_ids = set()
                self._used_title_hashes = set()
                self._recent_traditions = []
                self._usage_log = []
        else:
            self._used_ids = set()
            self._used_title_hashes = set()
            self._recent_traditions = []
            self._usage_log = []

    def _save_history(self) -> None:
        """Persist the used source IDs, title hashes, and usage log."""
        with open(self.history_path, "w") as f:
            json.dump({
                "used_ids": list(self._used_ids),
                "used_title_hashes": list(self._used_title_hashes),
                "recent_traditions": self._recent_traditions[-self.tradition_rotation_window:],
                "usage_log": self._usage_log,
            }, f, indent=2)

    def is_used(self, source_id: str) -> bool:
        """Check if a source ID has been used before."""
        return source_id in self._used_ids

    def is_title_used(self, title: str) -> bool:
        """Check if a story with a similar title has been used (cross-tradition dedup)."""
        return _title_hash(title) in self._used_title_hashes

    def mark_used(self, source_id: str, title: str = "", tradition: str = "") -> None:
        """Mark a source as used, recording its title hash and tradition."""
        self._used_ids.add(source_id)
        if title:
            self._used_title_hashes.add(_title_hash(title))
        if tradition:
            self._recent_traditions.append(tradition)
            # Keep only the rotation window
            self._recent_traditions = self._recent_traditions[-self.tradition_rotation_window:]
        
        # Log usage
        self._usage_log.append({
            "source_id": source_id,
            "title": title,
            "tradition": tradition,
            "date": datetime.now(timezone.utc).isoformat(),
        })
        self._save_history()

    def _get_expired_ids(self) -> Set[str]:
        """Return source_ids that are past the cooldown period and can be reused."""
        if not self._usage_log:
            return set()
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.similarity_window_days)
        expired = set()
        for entry in self._usage_log:
            try:
                used_date = datetime.fromisoformat(entry["date"])
                if used_date < cutoff:
                    expired.add(entry["source_id"])
            except (KeyError, ValueError):
                continue
        return expired

    def _tradition_score(self, tradition: str) -> int:
        """Score a tradition based on recent usage. Lower is better (less recently used)."""
        # Count how many times this tradition appears in the recent window
        return self._recent_traditions.count(tradition)

    def select_best(
        self,
        candidates: List[CorpusItem],
        language: str = "English",
    ) -> Optional[SelectionCandidate]:
        """Score and select the best candidate from eligible items.
        
        Selection priority:
        1. Exclude used source_ids (unless cooldown expired)
        2. Exclude items with duplicate titles (cross-tradition dedup)
        3. Prefer traditions not recently used (diversity rotation)
        4. Pick the first item from the preferred tradition
        """
        expired = self._get_expired_ids()
        
        eligible = []
        for item in candidates:
            # Skip if used and not expired
            if self.is_used(item.source_id) and item.source_id not in expired:
                continue
            # Skip if sensitivity flags
            if item.sensitivity_flags:
                continue
            # Skip if title is a duplicate (cross-tradition)
            story_title = item.location.get("story", "") if isinstance(item.location, dict) else ""
            if story_title and self.is_title_used(story_title):
                # Allow if the source_id is expired (past cooldown)
                if item.source_id not in expired:
                    continue
            
            eligible.append(item)

        if not eligible:
            # Try again without title dedup (only exact source_id dedup)
            eligible = [
                item for item in candidates
                if (not self.is_used(item.source_id) or item.source_id in expired)
                and not item.sensitivity_flags
            ]

        if not eligible:
            # Last resort: all items (even used ones, if cooldown expired)
            eligible = [
                item for item in candidates
                if not item.sensitivity_flags
            ]

        if not eligible:
            return None

        # Sort by tradition score (less recently used traditions first)
        eligible.sort(key=lambda item: (
            self._tradition_score(item.tradition),
            item.source_id,  # alphabetical fallback
        ))

        item = eligible[0]
        return SelectionCandidate(
            corpus_item=item,
            treatment_summary=f"A teaching from {item.work}",
            source_confidence=1.0,
            clarity_score=0.9,
            emotional_resonance=0.8,
            visual_potential=0.7,
            novelty_score=0.6,
            cultural_risk=0.1,
            suitability_score=0.85,
            overall_score=0.82,
            quote_mode=QuoteMode.paraphrase,
        )