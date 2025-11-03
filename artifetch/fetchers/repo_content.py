from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple
from urllib.parse import quote as urlquote, urlparse
from contextlib import contextmanager
import requests

Kind = Literal["repo", "dir", "file", "auto"]


@dataclass(frozen=True)
class _RepoRequest:
    # GitLab only
    namespace: str
    repo: str
    branch: str  # branch/tag/sha or "HEAD"
    path: Optional[str]  # None for repo; for dir/file it's the subpath
    kind: Kind = "auto"
    api_base: Optional[str] = None  # per-request override (used when parsing full https URL)


class RepoContentFetcher:
    """
    Fetch repository content (entire repo, subfolder, or single file) from GitLab.

    URI grammar (GitLab only):
        gitlab://{namespace}/{repo}[@{branch}][//{path}]

    Examples:
        fetch("gitlab://group/sub/repo", "out", kind="repo")
        fetch("gitlab://group/sub/repo@release/2025.10", "out", kind="repo")
        fetch("gitlab://group/sub/repo@main//services/auth", "out", kind="dir")
        fetch("gitlab://group/sub/repo@v1.2.3//CHANGELOG.md", "out", kind="file")

    Also accepted for convenience (auto-derive API base from URL host):
        gitlab://https://gitlab.example.com/group/repo/-/tree/<branch>/<path>
        gitlab://https://gitlab.example.com/group/repo/-/blob/<branch>/<path>
        gitlab://https://gitlab.example.com/group/repo  (branch=HEAD, path=None)

    Auth (optional):
        - GitLab: env GITLAB_TOKEN (sent as PRIVATE-TOKEN header)

    Self-hosted GitLab discovery:
        - ARTIFETCH_GITLAB_API_BASE (full base incl. "/api/v4") -> used as-is
        - ARTIFETCH_GIT_HOST (host or URL) -> builds "https://<host>/api/v4" or "<scheme>://<host>/<path>/api/v4"
        - Fallback -> "https://gitlab.com/api/v4"
    """

    GL_API_DEFAULT = "https://gitlab.com/api/v4"

    def __init__(self) -> None:
        self.gl_api_default = self._build_gitlab_api_base()

    # ---- Public API -----------------------------------------------------
    def fetch(self, uri: str, dest: Path | str, branch = None, kind: Kind = "auto") -> Path:
        req = self._parse_uri(uri)
        if kind != "auto":
            req = _RepoRequest(req.namespace, req.repo, req.branch, req.path, kind, req.api_base)

        dest_path = Path(dest)
        dest_path.mkdir(parents=True, exist_ok=True)

        # single file?
        if (req.kind == "file") or (req.kind == "auto" and req.path and _looks_like_file(req.path)):
            return self._gitlab_fetch_file(req, dest_path)

        # repo or dir via archive
        return self._gitlab_fetch_archive(req, dest_path)

    # ---- GitLab ---------------------------------------------------------
    def _gl_headers(self) -> dict:
        headers = {}
        token = os.getenv("GITLAB_TOKEN")
        if token:
            headers["PRIVATE-TOKEN"] = token
        return headers

    def _gitlab_project_id(self, req: _RepoRequest) -> str:
        # GitLab accepts URL-encoded "namespace/repo" as :id
        return urlquote(f"{req.namespace}/{req.repo}", safe="")

    def _api_base_for(self, req: _RepoRequest) -> str:
        return (req.api_base or self.gl_api_default).rstrip("/")

    def _gitlab_fetch_archive(self, req: _RepoRequest, dest: Path) -> Path:
        project_id = self._gitlab_project_id(req)
        url = f"{self._api_base_for(req)}/projects/{project_id}/repository/archive.zip"
        params: dict = {"sha": req.branch or "HEAD"}
        # For kind dir (or auto with path) ask server to pre-trim to that path
        if req.kind == "dir" or (req.path and req.kind == "auto"):
            params["path"] = (req.path or "").strip("/")

        with self._stream_to_temp(url, headers=self._gl_headers(), params=params) as zip_path:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if req.kind == "dir" or (req.path and req.kind == "auto"):
                    _extract_zip_subset(zf, subset_prefix=req.path, dest=dest)
                else:
                    _extract_zip_subset(zf, subset_prefix=None, dest=dest)
        return dest

    def _gitlab_fetch_file(self, req: _RepoRequest, dest: Path) -> Path:
        assert req.path, "File fetch requires a path"
        project_id = self._gitlab_project_id(req)
        file_enc = urlquote(req.path, safe="")
        url = f"{self._api_base_for(req)}/projects/{project_id}/repository/files/{file_enc}/raw"
        params = {"branch": req.branch or "HEAD"}
        target = dest / Path(req.path).name
        with requests.get(url, headers=self._gl_headers(), params=params, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return target

    # ---- Utilities ------------------------------------------------------
    def _parse_uri(self, uri: str) -> _RepoRequest:
        """
        Grammar:
            gitlab://<namespace>/<repo>
            gitlab://<namespace>/<repo>@<branch>
            gitlab://<namespace>/<repo>//<path>
            gitlab://<namespace>/<repo>@<branch>//<path>

        Convenience: if the part after scheme starts with http(s), treat it as a GitLab web URL.
        """
        if not uri.startswith("gitlab://"):
            raise ValueError(f"Unsupported URI scheme in '{uri}' (GitLab only)")
        rest = uri[len("gitlab://"):]

        if rest.startswith(("http://", "https://")):
            namespace, repo, branch, path, api_base = _parse_gitlab_https(rest)
            return _RepoRequest(namespace, repo, branch or "HEAD", path, "auto", api_base=api_base)

        namespace, repo, branch, path = _parse_rest_new_grammar(rest, allow_namespace=True)
        return _RepoRequest(namespace, repo, branch or "HEAD", path, "auto")

    @contextmanager
    def _stream_to_temp(self, url: str, headers: Optional[dict] = None, params: Optional[dict] = None):
        with requests.get(
            url,
            headers=headers or {},
            params=params or {},
            stream=True,
            allow_redirects=True,
            timeout=60,
        ) as r:
            r.raise_for_status()
            fd, tmp = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            try:
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            f.write(chunk)
                yield tmp
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    # --- GitLab base URL builder ----------------------------------------
    def _build_gitlab_api_base(self) -> str:
        """
        Precedence:
          1) ARTIFETCH_GITLAB_API_BASE (full base incl. /api/v4) -> used as-is
          2) ARTIFETCH_GIT_HOST with http/https scheme -> append /api/v4
          3) ARTIFETCH_GIT_HOST without scheme -> assume https and append /api/v4
          4) Fallback -> GL_API_DEFAULT
        """
        api_base = os.getenv("ARTIFETCH_GITLAB_API_BASE")
        if api_base:
            return api_base.rstrip("/")

        host = (os.getenv("ARTIFETCH_GIT_HOST") or "").strip().rstrip("/")
        if host:
            if host.startswith(("http://", "https://")):
                p = urlparse(host)
                base = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
                return f"{base}/api/v4"
            # no scheme -> default to https
            return f"https://{host}/api/v4"

        return self.GL_API_DEFAULT


# --------------------- parsing & extraction helpers ----------------------

def _parse_rest_new_grammar(rest: str, *, allow_namespace: bool) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    Parse the NEW grammar only:
      before = "<owner_or_ns>/<repo>"
      forms:
        before
        before@branch
        before//path
        before@branch//path
    """
    # 1) Split off the path (if provided), using the double-slash separator
    if "//" in rest:
        head, path = rest.split("//", 1)
        path = path or None
    else:
        head, path = rest, None

    # 2) Extract optional branch from head
    if "@" in head:
        before_at, branch = head.split("@", 1)
        branch = branch or None
    else:
        before_at, branch = head, None

    # 3) Split owner/namespace and repo
    parts = [p for p in before_at.split("/") if p]
    if allow_namespace:
        if len(parts) < 2:
            raise ValueError(f"Expected 'namespace/repo' in '{rest}'")
        repo = parts[-1]
        namespace = "/".join(parts[:-1])
    else:
        if len(parts) != 2:
            raise ValueError(f"Expected 'owner/repo' in '{rest}'")
        namespace, repo = parts

    return namespace, repo, branch, path


def _parse_gitlab_https(url: str) -> Tuple[str, str, Optional[str], Optional[str], str]:
    """Parse a GitLab *web* URL into (namespace, repo, branch, path, api_base).

    Supported examples:
      https://gitlab.example.com/group/repo
      https://gitlab.example.com/group/repo/-/tree/<branch>/<path>
      https://gitlab.example.com/group/repo/-/blob/<branch>/<path>
    """
    p = urlparse(url)
    api_base = f"{p.scheme}://{p.netloc}/api/v4"
    parts = [s for s in p.path.split("/") if s]
    if not parts:
        raise ValueError(f"Invalid GitLab URL: {url}")

    if "-" in parts:
        idx = parts.index("-")
        ns_repo_parts = parts[:idx]
        after = parts[idx + 1 :]
        # mode could be 'tree' or 'blob'
        if not ns_repo_parts:
            raise ValueError(f"Invalid GitLab URL: {url}")
        repo = ns_repo_parts[-1]
        namespace = "/".join(ns_repo_parts[:-1])
        if len(after) >= 2:
            # after = [tree|blob, branch, ...path]
            branch = after[1] or None
            subpath = "/".join(after[2:]) if len(after) > 2 else None
        else:
            branch = None
            subpath = None
    else:
        # No '/-/' segment -> repo root page
        if len(parts) < 2:
            raise ValueError(f"Invalid GitLab URL: {url}")
        repo = parts[-1]
        namespace = "/".join(parts[:-1])
        branch = None
        subpath = None

    return namespace, repo, branch, subpath, api_base


def _extract_zip_subset(zf: zipfile.ZipFile, subset_prefix: Optional[str], dest: Path) -> None:
    """
    Extract files from `zf` into `dest`.
    - Strips the *archive* top-level directory (GitLab zipballs include one).
    - If subset_prefix is provided (e.g., "path/to/dir"), only extracts entries under that
      prefix and flattens them so that 'path/to/dir/a/b.txt' => 'a/b.txt' relative to dest.
    """
    names = zf.namelist()
    if not names:
        return

    # Detect archive top-level folder (e.g., "owner-repo-<sha>/")
    top = names[0].split("/")[0] + "/"
    sp = subset_prefix.strip("/") if subset_prefix else None

    for name in names:
        if name.endswith("/"):
            continue  # skip dirs in zip listing
        rel = name
        if rel.startswith(top):
            rel = rel[len(top):]  # strip zip's top folder
        if sp:
            if rel == sp:
                continue  # skip the directory entry itself
            if rel.startswith(sp + "/"):
                rel = rel[len(sp) + 1 :]
            else:
                continue  # outside requested folder
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, length=128 * 1024)


def _looks_like_file(path: str) -> bool:
    return Path(path).suffix != ""