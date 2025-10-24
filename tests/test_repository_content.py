import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse as _urlparse

import pytest

# Adjust this import if you place the provider in a different module
from artifetch.providers.repository_content import RepositoryContentFetcher


# -----------------------------------------------------------------------------
# Test helpers: in-memory zipballs and a very small requests.get mock
# -----------------------------------------------------------------------------

def make_zipball(top_prefix: str, files: Dict[str, str]) -> bytes:
    """
    Create a zip file in memory whose entries are under `top_prefix` + relpath.
    `files` is {relative_path_in_repo_without_top_prefix: text_content}.
    """
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, content in files.items():
            arcname = f"{top_prefix.rstrip('/')}/{rel.lstrip('/')}"
            zf.writestr(arcname, content)
    return bio.getvalue()


@dataclass
class _FakeResponse:
    status_code: int
    body: bytes
    headers: Dict[str, str] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise AssertionError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=8192):
        # Yield in chunks to simulate streaming
        buf = memoryview(self.body)
        for i in range(0, len(buf), chunk_size):
            yield bytes(buf[i : i + chunk_size])

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class RequestsRouter:
    """
    A very small router for requests.get; routes by predicate(url, params)->_FakeResponse.
    """
    def __init__(self):
        self.routes: List[Tuple[Callable[[str, Optional[Dict[str, str]]], bool], _FakeResponse]] = []

    def register(self, pred: Callable[[str, Optional[Dict[str, str]]], bool], resp: _FakeResponse):
        self.routes.append((pred, resp))

    def get(self, url: str, headers=None, params=None, stream=False, allow_redirects=True, timeout=60):
        for pred, resp in self.routes:
            if pred(url, params):
                return resp
        raise AssertionError(f"No route matched URL={url!r} params={params!r}")


@pytest.fixture()
def req_router(monkeypatch):
    router = RequestsRouter()
    import requests
    monkeypatch.setattr(requests, "get", router.get)
    return router


@pytest.fixture()
def tmp_out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    return out

# -----------------------------------------------------------------------------
# GitHub helpers
# -----------------------------------------------------------------------------

def gh_zip_pred(owner: str, repo: str, ref: Optional[str]):
    base = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    if ref:
        base += f"/{ref}"
    def _p(url: str, params: Optional[Dict[str, str]]):
        return url.startswith(base)
    return _p

def gh_raw_pred(owner: str, repo: str, ref: str, path: str):
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"
    def _p(url: str, params: Optional[Dict[str, str]]):
        return url == raw
    return _p


# -----------------------------------------------------------------------------
# GitLab helpers
# -----------------------------------------------------------------------------

def gl_archive_pred(ns_repo: str, expect_sha: Optional[str] = None, expect_path: Optional[str] = None):
    proj_id = _urlparse.quote(ns_repo, safe="")
    base = f"https://gitlab.com/api/v4/projects/{proj_id}/repository/archive.zip"
    def _p(url: str, params: Optional[Dict[str, str]]):
        if url != base:
            return False
        if expect_sha is not None and (not params or params.get("sha") != expect_sha):
            return False
        if expect_path is not None and (not params or params.get("path") != expect_path.strip("/")):
            return False
        return True
    return _p

def gl_file_raw_pred(ns_repo: str, ref: str, file_path: str):
    proj_id = _urlparse.quote(ns_repo, safe="")
    encoded = _urlparse.quote(file_path, safe="")
    base = f"https://gitlab.com/api/v4/projects/{proj_id}/repository/files/{encoded}/raw"
    def _p(url: str, params: Optional[Dict[str, str]]):
        return url == base and params and params.get("ref") == ref
    return _p


# =============================================================================
#                               TESTS: GitHub
# =============================================================================

def test_github_download_full_repo_default_branch(req_router: RequestsRouter, tmp_out: Path):
    """
    - Full repository, default branch (provider may use zipball without explicit ref)
    - All repo files extracted under tmp_out (no top-level zip folder).
    """
    owner, repo, ref = "octocat", "hello", "main"
    top = f"{owner}-{repo}-abc123"
    files = {
        "README.md": "hi",
        "src/a.txt": "A",
        "docs/b.md": "B",
    }
    zip_bytes = make_zipball(top, files)

    req_router.register(gh_zip_pred(owner, repo, None), _FakeResponse(200, zip_bytes))
    req_router.register(gh_zip_pred(owner, repo, ref),  _FakeResponse(200, zip_bytes))  # allow explicit ref too

    provider = RepositoryContentProvider()
    out = provider.fetch(f"github://{owner}/{repo}@{ref}", tmp_out, kind="repo")

    # All files present and paths do NOT contain the zip's top folder
    assert (out / "README.md").read_text() == "hi"
    assert (out / "src" / "a.txt").read_text() == "A"
    assert (out / "docs" / "b.md").read_text() == "B"


def test_github_download_full_repo_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    owner, repo, ref = "octocat", "hello", "release-1.2"
    top = f"{owner}-{repo}-deadbeef"
    files = {"CHANGELOG.md": "1.2"}
    zip_bytes = make_zipball(top, files)

    req_router.register(gh_zip_pred(owner, repo, ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentProvider()
    out = provider.fetch(f"github://{owner}/{repo}@{ref}", tmp_out, kind="repo")

    assert (out / "CHANGELOG.md").read_text() == "1.2"


def test_github_download_subfolder_all_children(req_router: RequestsRouter, tmp_out: Path):
    """
    Download only a subfolder with all children.
    Ensures the extracted content does not include the parent tree above the subfolder.
    """
    owner, repo, ref = "octocat", "hello", "main"
    top = f"{owner}-{repo}-cafebabe"
    files = {
        "app/feature/x/config.yaml": "c: 1",
        "app/feature/x/impl.py": "print('x')",
        "app/feature/y/readme.txt": "y",         # outside the requested subfolder
        "LICENSE": "MIT",                        # outside the requested subfolder
    }
    zip_bytes = make_zipball(top, files)
    req_router.register(gh_zip_pred(owner, repo, ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentProvider()
    out = provider.fetch(f"github://{owner}/{repo}@{ref}/app/feature/x/", tmp_out, kind="dir")

    # Only the requested subfolder's content, and flattened relative to that folder
    assert (out / "config.yaml").read_text() == "c: 1"
    assert (out / "impl.py").read_text() == "print('x')"
    assert not (out / "app").exists()
    assert not (out / "feature").exists()
    assert not (out / "x").exists()
    assert not (out / "readme.txt").exists()
    assert not (out / "LICENSE").exists()


def test_github_download_subfolder_from_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    owner, repo, ref = "octocat", "hello", "hotfix"
    top = f"{owner}-{repo}-aaa000"
    files = {"path/a/b/hotfix.txt": "hf"}
    zip_bytes = make_zipball(top, files)
    req_router.register(gh_zip_pred(owner, repo, ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentProvider()
    out = provider.fetch(f"github://{owner}/{repo}@{ref}/path/a/b", tmp_out, kind="dir")

    # Flattened: only contents under 'path/a/b' should be present
    assert (out / "hotfix.txt").read_text() == "hf"
    assert list(out.iterdir()) == [out / "hotfix.txt"]


def test_github_download_single_file_default_branch(req_router: RequestsRouter, tmp_out: Path):
    owner, repo, ref = "octocat", "hello", "main"
    path = "docs/guide.md"
    content = "# hi"
    req_router.register(gh_raw_pred(owner, repo, ref, path), _FakeResponse(200, content.encode()))

    provider = RepositoryContentProvider()
    out_file = provider.fetch(f"github://{owner}/{repo}@{ref}/{path}", tmp_out, kind="file")

    assert out_file == tmp_out / "guide.md"
    assert out_file.read_text() == "# hi"


def test_github_download_single_file_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    owner, repo, ref = "octocat", "hello", "v2.0.0"
    path = "src/version.txt"
    content = "2.0.0"
    req_router.register(gh_raw_pred(owner, repo, ref, path), _FakeResponse(200, content.encode()))

    provider = RepositoryContentProvider()
    out_file = provider.fetch(f"github://{owner}/{repo}@{ref}/{path}", tmp_out, kind="file")

    assert out_file.read_text() == "2.0.0"


# =============================================================================
#                               TESTS: GitLab
# =============================================================================

def test_gitlab_download_full_repo_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref = "group/sub/monorepo", "main"
    top = "group-sub-monorepo-123456"
    files = {"README.md": "gldoc", "lib/a.py": "print(1)"}
    zip_bytes = make_zipball(top, files)

    req_router.register(gl_archive_pred(ns_repo, expect_sha=ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentProvider()
    out = provider.fetch(f"gitlab://{ns_repo}@{ref}", tmp_out, kind="repo")

    assert (out / "README.md").read_text() == "gldoc"
    assert (out / "lib" / "a.py").read_text() == "print(1)"


def test_gitlab_download_subfolder_only(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref = "group/sub/monorepo", "release/1.0"
    # Simulate GitLab server returning an archive that already contains only the requested subpath
    top = "group-sub-monorepo-654321"
    files = {"feature/only/here.txt": "X"}
    zip_bytes = make_zipball(top, files)

    req_router.register(
        gl_archive_pred(ns_repo, expect_sha=ref, expect_path="feature/only"),
        _FakeResponse(200, zip_bytes),
    )

    provider = RepositoryContentProvider()
    out = provider.fetch(f"gitlab://{ns_repo}@{ref}/feature/only", tmp_out, kind="dir")

    # Because server returned only that path, everything under it should be extracted flattened
    assert (out / "here.txt").read_text() == "X"
    assert not (out / "feature").exists()
    assert not (out / "only").exists()


def test_gitlab_download_single_file_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref, file_path = "group/sub/monorepo", "hotfix", "src/app.cfg"
    content = "k=v\n"
    req_router.register(gl_file_raw_pred(ns_repo, ref, file_path), _FakeResponse(200, content.encode()))

    provider = RepositoryContentProvider()
    out_file = provider.fetch(f"gitlab://{ns_repo}@{ref}/{file_path}", tmp_out, kind="file")

    assert out_file.name == "app.cfg"
    assert out_file.read_text() == "k=v\n"