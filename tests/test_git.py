import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from subprocess import CalledProcessError

from artifetch.providers.git import GitFetcher


@pytest.fixture
def tmp_dest(tmp_path):
    d = tmp_path / "repos"
    d.mkdir()
    return d


# --- _normalize_source (repo only) --- #

@pytest.mark.parametrize(
    "source, expected_repo",
    [
        ("https://github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("https://github.com/org/repo", "https://github.com/org/repo"),
        ("http://gitlab.com/org/repo", "http://gitlab.com/org/repo"),
        ("ssh://git@github.com/org/repo.git", "ssh://git@github.com/org/repo.git"),
        ("git@github.com:org/repo.git", "git@github.com:org/repo.git"),
        ("group/repo", "git@gitlab.com:group/repo.git"),
        ("group/sub/repo", "git@gitlab.com:group/sub/repo.git"),
    ]
)
def test_normalize_source_repo_only(source, expected_repo):
    f = GitFetcher()
    assert f._normalize_source(source) == expected_repo


# --- _validate_source_format --- #

@pytest.mark.parametrize("source", [
    # HTTPS/HTTP URLs (with/without userinfo)
    "https://github.com/org/repo.git",
    "https://github.com/org/repo",
    "https://user:token@github.com/org/repo.git",
    "http://gitlab.com/org/repo",
    # SSH URLs
    "ssh://git@github.com/org/repo.git",
    # SCP-style
    "git@github.com:org/repo.git",
    # Shorthand
    "group/repo",
    "group/subgroup/repo",
])
def test_validate_source_format_valid_inputs(source):
    fetcher = GitFetcher()
    fetcher._validate_source_format(source)  # Should not raise


@pytest.mark.parametrize("source", [
    # Stray '@' (legacy branch delimiter) should be rejected
    "group/repo@main",
    "group/sub/repo@feature/x",
    "git@github.com:org/repo.git@hotfix",
    "https://github.com/org/repo.git@dev",
    "http://gitlab.com/org/repo@feature/foo",
    # Malformed inputs
    "@",
    "@branch",
    "repo@",
    "invalidformat",
    "grouprepo",  # missing slash for shorthand
    "ftp://github.com/org/repo.git",  # unsupported scheme
])
def test_validate_source_format_invalid_inputs(source):
    fetcher = GitFetcher()
    with pytest.raises(ValueError, match="Invalid"):
        fetcher._validate_source_format(source)


# --- Fetch (mocked subprocess) --- #

@patch("artifetch.providers.git.subprocess.run")
def test_fetch_invokes_git_clone_with_branch(mock_run, tmp_dest):
    f = GitFetcher()
    source = "https://github.com/org/repo.git"
    branch = "dev"
    mock_run.return_value = MagicMock(returncode=0)

    result = f.fetch(source, tmp_dest, branch=branch)

    expected_dir = tmp_dest / "repo"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]

    assert cmd[1:4] == ["clone", "--depth", "1"]
    assert "-b" in cmd and "dev" in cmd
    assert str(expected_dir) in [str(Path(p)) for p in cmd]
    assert result == expected_dir


@patch("artifetch.providers.git.subprocess.run", side_effect=CalledProcessError(128, ["git"]))
def test_fetch_raises_on_failure(mock_run, tmp_dest):
    f = GitFetcher()
    with pytest.raises(RuntimeError, match="clone failed"):
        f.fetch("https://github.com/org/repo.git", tmp_dest)


@patch("artifetch.providers.git.Path.exists", return_value=True)
@patch("artifetch.providers.git.Path.iterdir", return_value=[Path("dummy.txt")])
def test_fetch_fails_if_target_dir_not_empty(mock_iterdir, mock_exists, tmp_path):
    fetcher = GitFetcher()
    with pytest.raises(RuntimeError, match="already exists and is not empty"):
        fetcher.fetch("https://github.com/org/repo.git", tmp_path)


@patch("artifetch.providers.git.subprocess.run")
def test_fetch_allows_at_in_branch(mock_run, tmp_dest):
    f = GitFetcher()
    source = "git@github.com:org/repo.git"
    branch = "feature@x"
    mock_run.return_value = MagicMock(returncode=0)

    f.fetch(source, tmp_dest, branch=branch)
    cmd = mock_run.call_args[0][0]
    assert "-b" in cmd and "feature@x" in cmd