"""Reads the TfL API key without adding a dotenv dependency."""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
KEY_NAME = "TFL_APP_KEY"


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse simple KEY=value lines; ignores blanks and comments."""
    if not path.exists():
        return {}
    pairs = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            pairs[key.strip()] = value.strip().strip("'\"")
    return pairs


def app_key_from_env(path: Path = ENV_FILE) -> str | None:
    """Real environment variable first, then the local .env file. Empty means no key."""
    return os.environ.get(KEY_NAME) or read_env_file(path).get(KEY_NAME) or None
