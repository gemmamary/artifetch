from __future__ import annotations
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from artifetch.utils.filesystem import ensure_dir


class GitFetcher:
    """
    Git repository fetcher (shallow clone by default).

    Usage examples:
      - HTTPS/SSH URL:
          https://github.com/org/repo.git
          ssh://git@github.com/org/repo.git
      - SCP-style:
          git@github.com:org/repo.git
      - GitLab-style shorthand:
          group/repo
          group/subgroup/repo

    New API:
      fetch(source, dest, branch=None)

      Pass branch explicitly (supports '@' and any valid git ref):
        fetch("group/repo", dest, branch="main")
        fetch("https://github.com/org/repo.git", dest, branch="feature@x")

    Env:
      - GIT_BINARY (optional) path to git, defaults to auto-detect or 'git'
    """

    def __init__(self):
        load_dotenv()
        self.git = os.getenv("GIT_BINARY") or shutil.which("git") or "git"

    def fetch(self, source: str, dest: Path, branch: Optional[str] = None) -> Path:
        dest = Path(dest).resolve()
        ensure_dir(dest)

        self._validate_source_format(source)
        repo_url = self._normalize_source(source)

        repo_name = Path(repo_url.rstrip("/").split("/")[-1]).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        target = dest / repo_name

        if target.exists() and any(target.iterdir()):
            raise RuntimeError(f"Destination '{target}' already exists and is not empty.")

        cmd = [self.git, "clone", "--depth", "1"]
        if branch:
            cmd += ["-b", branch]
        cmd += [repo_url, str(target)]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            sanitized = self._sanitize_userinfo_in_url(source)
            raise RuntimeError(f"git clone failed for source '{sanitized}': {e}") from e

        return target

    # ---------- helpers ----------

    def _validate_source_format(self, source: str) -> None:
        """
        Validates the *repository* part only.
        Accepts:
          - HTTPS / HTTP URLs
          - SSH URLs (ssh://)
          - SCP-style: git@host:org/repo.git
          - GitLab-style shorthand: group[/subgroup]/repo

        Rejects any stray '@' that appears to be used as a branch delimiter inside `source`.
        """
        # Reject unsupported schemes
        unsupported_schemes = ("ftp://", "file://", "s3://", "data://")
        if source.startswith(unsupported_schemes):
            raise ValueError(f"Invalid URL scheme in source: '{source}'")

        is_scp = source.startswith("git@") and (":" in source)
        is_url = source.startswith(("http://", "https://", "ssh://"))
        is_shorthand = ("/" in source) and not (is_url or is_scp)

        if not (is_url or is_scp or is_shorthand):
            raise ValueError(
                f"Invalid Git source format: '{source}'\n"
                "Expected a full Git URL (HTTPS/SSH/SCP) or GitLab-style shorthand like 'group/repo'."
            )

        # No legacy '@branch' allowed in source anymore
        if self._contains_stray_at_in_repo(source):
            raise ValueError(
                f"Invalid Git source format: '{source}'\n"
                "Detected '@' after the repository path. Pass the branch via the 'branch' parameter, "
                "e.g., fetch(source, dest, branch='...')."
            )

    def _normalize_source(self, src: str) -> str:
        """
        Returns a *repository URL* only (no branch), preserving full URLs and SCP style.
        Shorthand 'group/sub/repo' -> 'git@gitlab.com:group/sub/repo.git'
        """
        if src.startswith(("http://", "https://", "git@", "ssh://")):
            return src
        # GitLab-style SSH shorthand by default
        return f"git@gitlab.com:{src}.git"

    @staticmethod
    def _sanitize_userinfo_in_url(source: str) -> str:
        """Redacts userinfo in https URLs to avoid leaking tokens in error messages."""
        return re.sub(r"(https?://)([^@/]+)@", r"\1***@", source)

    @staticmethod
    def _contains_stray_at_in_repo(source: str) -> bool:
        """
        Detects whether `source` appears to include an '@' used as a branch delimiter.
        Rules (do not interfere with valid userinfo in netloc or scp 'git@host'):
          - For HTTP/HTTPS/SSH URLs: any '@' appearing *after* the end of the netloc (after the first '/' following '://') is stray.
          - For SCP-style 'git@host:org/repo.git': any '@' appearing after the first ':' is stray.
          - For shorthand: any '@' at all is stray.
        """
        if source.startswith(("http://", "https://", "ssh://")):
            scheme_end = source.find("://")
            if scheme_end == -1:
                return False
            pos = scheme_end + 3
            first_slash_after_netloc = source.find("/", pos)
            if first_slash_after_netloc == -1:
                # no path component; '@' in netloc may be userinfo; no stray '@' possible
                return False
            # Any '@' in the path portion is considered stray
            return "@" in source[first_slash_after_netloc + 1 :]

        if source.startswith("git@") and (":" in source):
            colon_idx = source.find(":")
            # Any '@' after the scp colon is stray
            return "@" in source[colon_idx + 1 :]

        # Shorthand: any '@' is stray
        if "/" in source:
            return "@" in source

        return False