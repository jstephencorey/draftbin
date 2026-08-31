import pytest
from fastapi.testclient import TestClient

from draftbin.app import ACCESS_COOKIE, create_app
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


def unlocked(client: TestClient) -> TestClient:
    """Reading a draft needs the access cookie. Set by hand rather than through the form
    so it stays non-Secure and survives a plain http test client."""
    client.cookies.set(ACCESS_COOKIE, TOKEN)
    return client


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield unlocked(test_client)


@pytest.fixture
def browser(app):
    """Someone holding a link and nothing else. https, or the cookie jar drops the Secure
    cookie; redirects stay unfollowed because where a form sends you is half of what is
    under test."""
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        yield client
