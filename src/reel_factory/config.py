import os
import yaml
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv


class Config:
    """Loads YAML config files and provides dot-notation access.

    The project root is auto-detected as the parent of this file's package
    directory (i.e. src/reel_factory/config.py → project root).
    Override with REEL_FACTORY_WORKDIR env var for non-standard layouts.
    """

    def __init__(self):
        # Load .env from CWD or project root
        load_dotenv()

        # Auto-detect project root: this file is at <root>/src/reel_factory/config.py
        self.root = Path(__file__).resolve().parent.parent.parent

        # Allow env override for deployment on a server with a different layout
        env_workdir = os.getenv("REEL_FACTORY_WORKDIR")
        if env_workdir:
            self.root = Path(env_workdir)

        self.config_dir = self.root / "config"
        self._settings: Dict[str, Any] = {}
        self.load_all()

    def load_all(self):
        """Loads all YAML files from the config directory."""
        if not self.config_dir.exists():
            return
        for yaml_file in self.config_dir.glob("*.yaml"):
            with open(yaml_file, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    for key, value in data.items():
                        if (
                            key in self._settings
                            and isinstance(self._settings[key], dict)
                            and isinstance(value, dict)
                        ):
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
    def workdir(self) -> Path:
        """Return the working directory for this project."""
        # Check config first, then env, then auto-detected root
        wd = self.get("app.workdir")
        if wd:
            return Path(wd)
        return self.root

    @property
    def runtime_dir(self) -> Path:
        """Return the runtime directory."""
        rd = self.get("app.runtime_dir", "runtime")
        return self.workdir / rd

    @property
    def env(self):
        """Access environment variables."""
        return os.environ


# Singleton instance for the application
config = Config()