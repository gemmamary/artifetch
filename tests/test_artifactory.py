import os
import io
import pytest
import requests
from pathlib import Path

from artifetch.providers.artifactory import ArtifactoryFetcher


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure env vars don't leak between tests."""
    for var in ["ARTIFACTORY_URL", "ARTIFACTORY_USER", "ARTIFACTORY_TOKEN", "ARTIFACTORY_PASSWORD"]:
        monkeypatch.delenv(var, raising=False)


# --- Initialization tests --- #

def test_init_raises_if_no_credentials(monkeypatch):
    """Fetcher should fail fast if user/token missing."""
    monkeypatch.setenv("ARTIFACTORY_URL", "https://myartifactory")
    with pytest.raises(ValueError, match="credentials missing"):
        ArtifactoryFetcher()


def test_init_succeeds_with_token(monkeypatch):
    """Should accept valid credentials."""
    monkeypatch.setenv("ARTIFACTORY_URL", "https://myartifactory")
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    f = ArtifactoryFetcher()
    assert f.base_url == "https://myartifactory"
    assert f.user == "user"
    assert f.token == "token"


# --- URL construction --- #

def test_builds_full_url_when_relative(monkeypatch, tmp_path, requests_mock):
    monkeypatch.setenv("ARTIFACTORY_URL", "https://example.jfrog.io/artifactory")
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    requests_mock.get(
        "https://example.jfrog.io/artifactory/libs-release/file.zip",
        content=b"data"
    )

    f = ArtifactoryFetcher()
    dest = f.fetch("libs-release/file.zip", tmp_path)

    assert dest.exists()
    assert dest.name == "file.zip"
    assert dest.read_bytes() == b"data"


def test_accepts_full_url(monkeypatch, tmp_path, requests_mock):
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    url = "https://example.jfrog.io/artifactory/libs-release/file2.zip"
    requests_mock.get(url, content=b"abc123")

    f = ArtifactoryFetcher()
    dest = f.fetch(url, tmp_path)

    assert dest.exists()
    assert dest.read_bytes() == b"abc123"


# --- Error handling --- #

def test_raises_on_http_error(monkeypatch, tmp_path, requests_mock):
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    url = "https://example.jfrog.io/artifactory/libs-release/missing.zip"
    requests_mock.get(url, status_code=404, text="Not Found")

    f = ArtifactoryFetcher()
    with pytest.raises(RuntimeError, match="Failed to download"):
        f.fetch(url, tmp_path)


def test_handles_network_exception(monkeypatch, tmp_path, mocker):
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    mock_get = mocker.patch("requests.get", side_effect=requests.exceptions.Timeout)

    f = ArtifactoryFetcher()
    with pytest.raises(RuntimeError, match="Failed to download"):
        f.fetch("https://example.com/file.zip", tmp_path)

    mock_get.assert_called_once()


# --- File writing and destination --- #

def test_creates_destination_dir(monkeypatch, tmp_path, requests_mock):
    monkeypatch.setenv("ARTIFACTORY_USER", "user")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "token")

    dest_dir = tmp_path / "nested" / "downloads"
    url = "https://example.jfrog.io/artifactory/libs-release/test.zip"
    requests_mock.get(url, content=b"test-data")

    f = ArtifactoryFetcher()
    file_path = f.fetch(url, dest_dir)

    assert file_path.exists()
    assert file_path.parent == dest_dir.resolve()
    assert file_path.read_bytes() == b"test-data"


# --- Authentication --- #

def test_uses_auth(monkeypatch, tmp_path, requests_mock):
    """Ensure HTTP Basic Auth headers use provided credentials."""
    monkeypatch.setenv("ARTIFACTORY_USER", "u")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "t")

    url = "https://example.jfrog.io/artifactory/libs-release/auth.zip"
    requests_mock.get(url, content=b"ok")

    f = ArtifactoryFetcher()
    f.fetch(url, tmp_path)

    req = requests_mock.request_history[0]
    assert req.headers["Authorization"].startswith("Basic")


# --- Edge cases --- #

def test_empty_response(monkeypatch, tmp_path, requests_mock):
    """Should create an empty file if server returns nothing."""
    monkeypatch.setenv("ARTIFACTORY_USER", "u")
    monkeypatch.setenv("ARTIFACTORY_TOKEN", "t")

    url = "https://example.jfrog.io/artifactory/libs-release/empty.zip"
    requests_mock.get(url, content=b"")

    f = ArtifactoryFetcher()
    path = f.fetch(url, tmp_path)
    assert path.exists()
    assert path.stat().st_size == 0
