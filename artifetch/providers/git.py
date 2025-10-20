from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple
from dotenv import load_dotenv
from artifetch.utils.filesystem import ensure_dir


class GitFetcher:
    """
    Git repository fetcher (shallow clone by default).

    Usage examples:
      - HTTPS/SSH:
          https://github.com/org/repo.git
          git@gitlab.com:group/repo.git
      - Shorthand with branch:
          group/repo@main

    Env:
      - GIT_BINARY (optional) path to git, defaults to auto-detect or 'git'
    """

    def __init__(self):
        load_dotenv()
        self.git = os.getenv("GIT_BINARY") or shutil.which("git") or "git"

    def fetch(self, source: str, dest: Path) -> Path:
        dest = Path(dest).resolve()
        ensure_dir(dest)

        repo_url, branch = self._normalize_source(source)

        # Clone target directory name = repo name (without .git)
        repo_name = Path(repo_url.rstrip("/").split("/")[-1]).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        target = dest / repo_name

        cmd = [self.git, "clone", "--depth", "1"]
        if branch:
            cmd += ["-b", branch]
        cmd += [repo_url, str(target)]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"git clone failed: {e}") from e

        return target

    # ---------- helpers ----------

    def _normalize_source(self, src: str) -> Tuple[str, str | None]:
        """
        Accepts:
          - Full SSH/HTTPS URLs (returns unchanged)
          - Shorthand 'group/repo@branch' → 'git@gitlab.com:group/repo.git', branch
          - Shorthand 'group/repo' → default branch ('main' if set) or server default
        """
        # If it's already a URL or SSH, pass through
        if src.startswith(("http://", "https://", "git@", "ssh://")):
            repo, branch = self._split_branch(src)
            return repo, branch

        # Otherwise assume GitLab-style SSH shorthand
        repo_part, branch = self._split_branch(src)
        repo_url = f"git@gitlab.com:{repo_part}.git"
        return repo_url, branch

    @staticmethod
    def _split_branch(s: str) -> Tuple[str, str | None]:
        if "@" in s:
            repo, branch = s.split("@", 1)
            return repo, branch or None
        return s, None

