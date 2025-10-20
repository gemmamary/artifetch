


# tests/providers/test_gitlab.py

import io
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from artifetch.providers.gitlab import GitLabFetcher


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for v in ["GITLAB_URL", "GITLAB_TOKEN", "CI_JOB_TOKEN"]:
        monkeypatch.delenv(v, raising=False)


# --- Initialization --- #

def test_init_raises_if_no_token(monkeypatch):
    with pytest.raises(ValueError, match="GitLab token missing"):
        GitLabFetcher()


def test_init_uses_ci_job_token(monkeypatch):
    monkeypatch.setenv("CI_JOB_TOKEN", "abc123")
    f = GitLabFetcher()
    assert f.token == "abc123"


def test_init_with_gitlab_url(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    f = GitLabFetcher()
    assert f.url == "https://gitlab.example.com"
    assert f.token == "tok"


# --- URL Parsing --- #

def test_parse_full_url_extracts_job_id():
    f = GitLabFetcher()
    proj, job = f._parse_full_url(
        "https://gitlab.example.com/group/project/-/jobs/42/artifacts/download"
    )
    assert proj == "group/project"
    assert job == 42


def test_parse_shorthand_works():
    f = GitLabFetcher()
    proj, job = f._parse_shorthand("group/project/-/jobs/123/artifacts.zip")
    assert proj == "group/project"
    assert job == 123


def test_parse_shorthand_bad_format():
    f = GitLabFetcher()
    with pytest.raises(ValueError):
        f._parse_shorthand("group/project/jobs/123.zip")


# --- Fetching (mocked) --- #

@patch("artifetch.providers.gitlab.gitlab.Gitlab")
def test_fetch_downloads_artifact(MockGitlab, tmp_path, monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "token")

    fake_job = MagicMock()
    fake_job.artifacts = lambda streamed, action: action(b"data123")

    fake_project = MagicMock()
    fake_project.jobs.get.return_value = fake_job

    mock_gl = MockGitlab.return_value
    mock_gl.projects.get.return_value = fake_project

    f = GitLabFetcher()
    result_path = f.fetch("group/project/-/jobs/1/artifacts.zip", tmp_path)

    assert result_path.exists()
    assert result_path.read_bytes() == b"data123"

    MockGitlab.assert_called_once_with("https://gitlab.example.com", private_token="token", timeout=60)
    fake_project.jobs.get.assert_called_once_with(1)
