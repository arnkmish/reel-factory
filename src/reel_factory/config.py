import os
import yaml
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()
        self.root = Path(__file__).parent.parent.parent
        self.config_dir = self.root / "config"
        self._settings: Dict[str, Any] = {}
        self.load_all()

    def load_all(self):
        """Loads all YAML files from the config directory."""
        for yaml_file in self.config_dir.glob("*.yaml"):
            with open(yaml_file, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    # Use a deep merge if keys overlap, otherwise simple update
                    # This handles cases where multiple files define top-level keys
                    for key, value in data.items():
                        if key in self._settings and isinstance(self._settings[key], dict) and isinstance(value, dict):
                            self._settings[key].update(value)
                        else:
                            self._settings[key] = value

    def get(self, key_path: str, default: Any = None) -> Any:
        """Retrieve a setting using dot-notation (e.g., 'app.language')."""
        keys = key_path.split(".")
        val = self._settings
        try:
            for k in keys:
                val = val[k]
            return val
        except (KeyError, TypeError):
            return default

    @property
    def env(self):
        """Access environment variables."""
        return os.environ

# Singleton instance for the application
config = Config()
