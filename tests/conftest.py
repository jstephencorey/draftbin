import pytest
from fastapi.testclient import TestClient

from draftbin.app import create_app
from draftbin.config import DEFAULT_MAX_TTL_SECONDS, DEFAULT_TTL_SECONDS, Config

TOKEN = "test-token-with-enough-length"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        token=TOKEN,
        public_base_url="https://drafts.example.com",
        data_dir=tmp_path,
        default_ttl_seconds=DEFAULT_TTL_SECONDS,
        max_ttl_seconds=DEFAULT_MAX_TTL_SECONDS,
        max_upload_bytes=2 * 1024 * 1024,
        sweep_interval_seconds=3600,
    )


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
