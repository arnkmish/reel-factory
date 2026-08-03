import pytest
from reel_factory.config import config

def test_config_loads_app_name():
    # Test that the config can retrieve a value from app.yaml
    assert config.get("app.name") == "Reel Factory"

def test_config_loads_threshold():
    # Test that the config can retrieve a value from review_thresholds.yaml
    assert config.get("review.pass_threshold") == 8.0

def test_config_returns_default_for_missing():
    assert config.get("non.existent.key", "default_val") == "default_val"
