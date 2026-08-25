import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from draftbin.templates import THEMES

DEFAULT_TTL_SECONDS = 48 * 60 * 60
DEFAULT_MAX_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
DEFAULT_SWEEP_INTERVAL_SECONDS = 5 * 60
DEFAULT_TOMBSTONE_RETENTION_SECONDS = 30 * 24 * 60 * 60


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    public_base_url: str
    data_dir: Path
    default_ttl_seconds: int
    max_ttl_seconds: int
    max_upload_bytes: int
    sweep_interval_seconds: int
    tombstone_retention_seconds: int = DEFAULT_TOMBSTONE_RETENTION_SECONDS
    theme: str = "auto"
    timezone: str = "UTC"

    @property
    def display_zone(self) -> ZoneInfo:
        """Only for dates shown to a reader; the API keeps reporting UTC."""
        return ZoneInfo(self.timezone)

    @property
    def cookies_are_secure(self) -> bool:
        """A Secure cookie is dropped over plain http, which would break local dev."""
        return self.public_base_url.startswith("https://")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "draftbin.sqlite3"

    @property
    def drafts_dir(self) -> Path:
        return self.data_dir / "drafts"

    def draft_url(self, draft_id: str) -> str:
        return f"{self.public_base_url}/d/{draft_id}"


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from error
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


def load_config() -> Config:
    token = os.environ.get("DRAFTBIN_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "DRAFTBIN_TOKEN is required. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if len(token) < 20:
        raise ConfigError(f"DRAFTBIN_TOKEN must be at least 20 characters, got {len(token)}")

    theme = os.environ.get("DRAFTBIN_THEME", "auto").strip().lower() or "auto"
    if theme not in THEMES:
        raise ConfigError(f"DRAFTBIN_THEME must be one of {', '.join(THEMES)}, got {theme!r}")

    timezone_name = os.environ.get("DRAFTBIN_TIMEZONE", "UTC").strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConfigError(
            f"DRAFTBIN_TIMEZONE must be an IANA name like America/Denver, got {timezone_name!r}"
        ) from error

    default_ttl = positive_int_env("DRAFTBIN_DEFAULT_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    max_ttl = positive_int_env("DRAFTBIN_MAX_TTL_SECONDS", DEFAULT_MAX_TTL_SECONDS)
    if default_ttl > max_ttl:
        raise ConfigError(
            f"DRAFTBIN_DEFAULT_TTL_SECONDS ({default_ttl}) exceeds "
            f"DRAFTBIN_MAX_TTL_SECONDS ({max_ttl})"
        )

    return Config(
        token=token,
        public_base_url=os.environ.get(
            "DRAFTBIN_PUBLIC_BASE_URL", "http://localhost:8000"
        ).rstrip("/"),
        data_dir=Path(os.environ.get("DRAFTBIN_DATA_DIR", ".local")),
        default_ttl_seconds=default_ttl,
        max_ttl_seconds=max_ttl,
        max_upload_bytes=positive_int_env("DRAFTBIN_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
        sweep_interval_seconds=positive_int_env(
            "DRAFTBIN_SWEEP_INTERVAL_SECONDS", DEFAULT_SWEEP_INTERVAL_SECONDS
        ),
        tombstone_retention_seconds=positive_int_env(
            "DRAFTBIN_TOMBSTONE_RETENTION_SECONDS", DEFAULT_TOMBSTONE_RETENTION_SECONDS
        ),
        theme=theme,
        timezone=timezone_name,
    )
