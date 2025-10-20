import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from artifetch.providers.git import GitFetcher


@pytest.fixture
def tmp_dest(tmp_path):
    d = tmp_path / "repos"
    d.mkdir()
    return d


# --- Normalization --- #

def test_split_branch_with_and_without():
    f = GitFetcher()
    repo, branch = f._split_branch("group/repo@main")
    assert repo == "group/repo"
    assert branch == "main"

    repo, branch = f._split_branch("group/repo")
    assert branch is None


def test_normalize_http_url():
    f = GitFetcher()
    repo, branch = f._normalize_source("https://github.com/org/repo.git@dev")
    assert repo.startswith("https://")
    assert branch == "dev"


def test_normalize_shorthand_defaults_to_gitlab():
    f = GitFetcher()
    repo, branch = f._normalize_source("group/repo@main")
    assert repo.startswith("git@gitlab.com:")
    assert repo.endswith(".git")
    assert branch == "main"


# --- Fetch (mocked subprocess) --- #

@patch("artifetch.providers.git.subprocess.run")
def test_fetch_invokes_git_clone(mock_run, tmp_dest):
    f = GitFetcher()
    source = "https://github.com/org/repo.git"
    mock_run.return_value = MagicMock(returncode=0)

    result = f.fetch(source, tmp_dest)

    expected_dir = tmp_dest / "repo"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "git" in cmd[0]
    assert "--depth" in cmd
    assert str(expected_dir) in cmd
    assert result == expected_dir


@patch("artifetch.providers.git.subprocess.run", side_effect=Exception("clone failed"))
def test_fetch_raises_on_failure(mock_run, tmp_dest):
    f = GitFetcher()
    with pytest.raises(RuntimeError, match="clone failed"):
        f.fetch("https://github.com/org/repo.git", tmp_dest)
