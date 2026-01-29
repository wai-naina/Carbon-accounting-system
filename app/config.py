from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"


@dataclass
class AppConfig:
    settings: Dict[str, Any]

    def get(self, *keys: str, default: Any | None = None) -> Any:
        current: Any = self.settings
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    @property
    def db_path(self) -> Path:
        db_path = self.get("database", "path", default="data/octavia.db")
        return BASE_DIR / db_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_SETTINGS_PATH
    if not config_path.exists():
        return AppConfig(settings={})
    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return AppConfig(settings=data)


def ensure_directories() -> None:
    config = load_config()
    db_path = config.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    uploads_dir = BASE_DIR / "data" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
