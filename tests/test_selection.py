import json
import tempfile
from pathlib import Path

import pytest

from reel_factory.corpus import Corpus
from reel_factory.models import CorpusItem, RiskTier


@pytest.fixture
def corpus_dir():
    """Create a temporary corpus directory with sample items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir(parents=True)

        items = [
            {
                "source_id": "gita-2-47",
                "tradition": "Hindu",
                "work": "Bhagavad Gita",
                "approved_translation": "Do your duty without attachment.",
                "license": "public-domain",
                "source_url": "https://example.com/gita",
                "sensitivity_flags": [],
                "risk_tier": "low",
            },
            {
                "source_id": "panchatantra-1",
                "tradition": "Indian Fable",
                "work": "Panchatantra",
                "approved_translation": "The clever fox...",
                "license": "public-domain",
                "source_url": "https://example.com/panchatantra",
                "sensitivity_flags": [],
                "risk_tier": "low",
            },
            {
                "source_id": "sensitive-1",
                "tradition": "Test",
                "work": "Sensitive Work",
                "approved_translation": "Sensitive content.",
                "license": "public-domain",
                "source_url": "https://example.com/sensitive",
                "sensitivity_flags": ["disputed"],
                "risk_tier": "high",
            },
        ]

        with open(manifest_dir / "sample.json", "w") as f:
            json.dump(items, f)

        yield Path(tmpdir)


def test_corpus_loads_items(corpus_dir):
    corpus = Corpus(corpus_dir)
    corpus.load()
    assert corpus.count() == 3


def test_corpus_get_eligible_filters_sensitive(corpus_dir):
    corpus = Corpus(corpus_dir)
    eligible = corpus.get_eligible()
    assert len(eligible) == 2
    assert all(item.source_id != "sensitive-1" for item in eligible)


def test_corpus_get_by_tradition(corpus_dir):
    corpus = Corpus(corpus_dir)
    hindu_items = corpus.get_by_tradition("Hindu")
    assert len(hindu_items) == 1
    assert hindu_items[0].source_id == "gita-2-47"


def test_corpus_get_by_risk_tier(corpus_dir):
    corpus = Corpus(corpus_dir)
    low_risk = corpus.get_by_risk_tier(RiskTier.low)
    assert len(low_risk) == 2


def test_corpus_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus = Corpus(tmpdir)
        corpus.load()
        assert corpus.count() == 0
