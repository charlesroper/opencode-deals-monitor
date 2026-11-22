"""Settings and environment variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Run settings. Every field can be overridden by an environment variable."""

    models_api_url: str
    console_go_url: str
    public_base_url: str
    feed_title: str
    history_limit: int
    data_dir: Path
    public_dir: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        """Build settings from ``os.environ`` (or an injected env mapping)."""
        e = os.environ if env is None else env
        return cls(
            models_api_url=e.get("MODELS_API_URL", "https://models.dev/api.json"),
            console_go_url=e.get("CONSOLE_GO_URL", "https://opencode.ai/console/go"),
            public_base_url=e.get(
                "PUBLIC_BASE_URL", "https://example.github.io/opencode-deals-monitor"
            ),
            feed_title=e.get("FEED_TITLE", "OpenCode Go Deals Monitor"),
            history_limit=int(e.get("HISTORY_LIMIT", "30")),
            data_dir=Path(e.get("DATA_DIR", "data")),
            public_dir=Path(e.get("PUBLIC_DIR", "public")),
        )

    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def history_path(self) -> Path:
        return self.data_dir / "history.json"

    @property
    def feed_path(self) -> Path:
        return self.public_dir / "feed.xml"

    @property
    def html_path(self) -> Path:
        return self.public_dir / "index.html"

    @property
    def deals_path(self) -> Path:
        return self.public_dir / "deals.json"
