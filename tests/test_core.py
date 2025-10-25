from pathlib import Path
from typing import Dict, Any, Type, cast
import pytest

from artifetch.fetchers.repo_clone import RepoCloneFetcher
from artifetch.core import fetch, FETCHERS  # adjust import

def test_core_forwards_branch_and_returns_path(monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = {}

    class SpyClone(RepoCloneFetcher):
        def fetch(self, source: str, dest: Path, branch: str | None = None) -> Path:  # type: ignore[override]
            # record forwarded args
            calls["args"] = (source, dest, branch)
            # emulate a successful clone return value (what your fetcher would return)
            return dest / "monorepo"

    # swap the fetcher in the registry just for this test
    monkeypatch.setitem(FETCHERS, "repo_clone", SpyClone)

    result = fetch(
        source="group/monorepo",
        dest=str(out),
        provider="repo_clone",
        branch="mybranch",
    )

    # 1) forwarding assertions (note: dest is resolved in core.fetch())
    assert calls["args"][0] == "group/monorepo"
    assert calls["args"][1] == out.resolve()
    assert calls["args"][2] == "mybranch"

    # 2) return contract: Path to the cloned repo
    assert result == out.resolve() / "monorepo"
    assert isinstance(result, Path)