import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from artifetch.core import fetch as core_fetch


@patch("artifetch.core.RepoCloneFetcher.fetch")
def test_core_forwards_branch_to_git(mock_git_fetch, tmp_path):
    src = "group/monorepo"
    dest = tmp_path / "out"
    dest.mkdir()
    branch = "dev@can"

    expected_path = dest / "monorepo"
    mock_git_fetch.return_value = expected_path

    result = core_fetch(src, dest=str(dest), provider="git", branch=branch)

    assert result == expected_path
    # Validate call forwarding with kwargs
    mock_git_fetch.assert_called_once()
    args, kwargs = mock_git_fetch.call_args
    assert args[0] == src
    assert args[1] == dest.resolve()
    assert kwargs["branch"] == branch