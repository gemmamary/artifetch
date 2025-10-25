import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse as _urlparse
import os
import pytest

# Adjust this import if you place the provider in a different module
from artifetch.fetchers.repo_content import RepositoryContentFetcher

# -------------------------------------------------------------------------
# Test helpers: in-memory zipballs and a very small requests.get mock
# -------------------------------------------------------------------------

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


# -------------------------------------------------------------------------
# GitLab helpers
# -------------------------------------------------------------------------

def gl_archive_pred(base: str, ns_repo: str, expect_sha: Optional[str] = None, expect_path: Optional[str] = None):
    proj_id = _urlparse.quote(ns_repo, safe="")
    full = f"{base.rstrip('/')}/projects/{proj_id}/repository/archive.zip"

    def _p(url: str, params: Optional[Dict[str, str]]):
        if url != full:
            return False
        if expect_sha is not None and (not params or params.get("sha") != expect_sha):
            return False
        if expect_path is not None and (not params or params.get("path") != expect_path.strip("/")):
            return False
        return True

    return _p


def gl_file_raw_pred(base: str, ns_repo: str, ref: str, file_path: str):
    proj_id = _urlparse.quote(ns_repo, safe="")
    encoded = _urlparse.quote(file_path, safe="")
    full = f"{base.rstrip('/')}/projects/{proj_id}/repository/files/{encoded}/raw"

    def _p(url: str, params: Optional[Dict[str, str]]):
        return url == full and params and params.get("ref") == ref

    return _p


# =============================================================================
# TESTS: GitLab public (gitlab.com)
# =============================================================================

def test_gitlab_download_full_repo_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref = "group/sub/monorepo", "main"
    base = "https://gitlab.com/api/v4"
    top = "group-sub-monorepo-123456"
    files = {"README.md": "gldoc", "lib/a.py": "print(1)"}
    zip_bytes = make_zipball(top, files)
    req_router.register(gl_archive_pred(base, ns_repo, expect_sha=ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentFetcher()
    out = provider.fetch(f"gitlab://{ns_repo}@{ref}", tmp_out, kind="repo")
    assert (out / "README.md").read_text() == "gldoc"
    assert (out / "lib" / "a.py").read_text() == "print(1)"


def test_gitlab_download_subfolder_only(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref = "group/sub/monorepo", "release/1.0"
    base = "https://gitlab.com/api/v4"
    top = "group-sub-monorepo-654321"
    files = {"feature/only/here.txt": "X"}
    zip_bytes = make_zipball(top, files)
    req_router.register(gl_archive_pred(base, ns_repo, expect_sha=ref, expect_path="feature/only"), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentFetcher()
    out = provider.fetch(f"gitlab://{ns_repo}@{ref}//feature/only", tmp_out, kind="dir")
    # Flattened within destination
    assert (out / "here.txt").read_text() == "X"
    assert not (out / "feature").exists()
    assert not (out / "only").exists()


def test_gitlab_download_single_file_specific_branch(req_router: RequestsRouter, tmp_out: Path):
    ns_repo, ref, file_path = "group/sub/monorepo", "hotfix", "src/app.cfg"
    base = "https://gitlab.com/api/v4"
    content = "k=v\n"
    req_router.register(gl_file_raw_pred(base, ns_repo, ref, file_path), _FakeResponse(200, content.encode()))

    provider = RepositoryContentFetcher()
    out_file = provider.fetch(f"gitlab://{ns_repo}@{ref}//{file_path}", tmp_out, kind="file")
    assert out_file.name == "app.cfg"
    assert out_file.read_text() == "k=v\n"


# =============================================================================
# TESTS: GitLab private/self-hosted
# =============================================================================

def test_gitlab_scheme_with_https_url_is_parsed_as_https(monkeypatch, req_router, tmp_out):
    url = "https://git-gdd.sdo.jlrmotor.com/ADAS/loki/cross-collaboration/dadc-test-automation/-/tree/release/1.0/services/smoke"
    ns_repo = "ADAS/loki/cross-collaboration/dadc-test-automation"
    ref = "release/1.0"
    top = "adas-loki-123"
    zip_bytes = make_zipball(top, {"services/smoke/a.txt": "x"})  # subset doesn't matter
    from urllib.parse import quote

    proj_id = quote(ns_repo, safe="")
    base = "https://git-gdd.sdo.jlrmotor.com/api/v4"

    req_router.register(
        lambda u, p: u == f"{base}/projects/{proj_id}/repository/archive.zip" and p == {"sha": ref, "path": "services/smoke"},
        _FakeResponse(200, zip_bytes),
    )

    out = RepositoryContentFetcher().fetch(f"gitlab://{url}", tmp_out, kind="dir")
    assert (out / "a.txt").read_text() == "x"


def test_gitlab_private_full_repo_via_env_host(monkeypatch, req_router: RequestsRouter, tmp_out: Path):
    # Point provider to a private host via ARTIFETCH_GIT_HOST
    monkeypatch.setenv("ARTIFETCH_GIT_HOST", "git.private.example")
    base = "https://git.private.example/api/v4"
    ns_repo, ref = "team/app", "develop"
    top = "team-app-111"
    files = {"README.md": "private", "mod/b.py": "print(2)"}
    zip_bytes = make_zipball(top, files)
    req_router.register(gl_archive_pred(base, ns_repo, expect_sha=ref), _FakeResponse(200, zip_bytes))

    provider = RepositoryContentFetcher()
    out = provider.fetch(f"gitlab://{ns_repo}@{ref}", tmp_out, kind="repo")
    assert (out / "README.md").read_text() == "private"
    assert (out / "mod" / "b.py").read_text() == "print(2)"


def test_gitlab_private_single_file_via_env_api_base(monkeypatch, req_router: RequestsRouter, tmp_out: Path):
    # Point provider to an explicit API base
    monkeypatch.setenv("ARTIFETCH_GITLAB_API_BASE", "https://git.myco.local/custom/api/v4")
    base = "https://git.myco.local/custom/api/v4"
    ns_repo, ref, file_path = "org/service", "v3.1", "conf/settings.yaml"
    content = "flag: true\n"
    req_router.register(gl_file_raw_pred(base, ns_repo, ref, file_path), _FakeResponse(200, content.encode()))

    provider = RepositoryContentFetcher()
    out_file = provider.fetch(f"gitlab://{ns_repo}@{ref}//{file_path}", tmp_out, kind="file")
    assert out_file.name == "settings.yaml"
    assert out_file.read_text() == "flag: true\n"