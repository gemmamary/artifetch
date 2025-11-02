from __future__ import annotations
import os
import re
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional
try:
    from dotenv import load_dotenv  # optional
except Exception:  
    def load_dotenv() -> None:
        return

from artifetch.utils.filesystem import ensure_dir

logger = logging.getLogger(__name__)


class RepoCloneFetcher:
    """
    Repository Clone fetcher (shallow clone using git by default).
    To use a specific version of git, pass in path to the git .exe on the machine this is being executed from.
    If the GIT_BINARY environment variable is not set, default git command will be used.

    Usage:
      # Full repo (default branch):
      fetch("https://gitlab.com/org/repo.git", dest)

      # Specific branch:
      fetch("git@gitlab.com:org/repo.git", dest, branch="release/2025.10")

    Notes:
      - If `branch` is None, we omit `-b` so Git uses the remote default branch.
    """

    def __init__(self):
        load_dotenv()
        self.git = os.getenv("GIT_BINARY") or shutil.which("git") or "git"

    def fetch(self, source: str, dest: Path, branch: Optional[str] = None) -> Path:
        
        dest = Path(dest).resolve()
        ensure_dir(dest)
        logger.debug("Validating source format...")
        self._validate_source_format(source)
        logger.debug("Normalizing (shorthand -> Full URL)")
        repo_url = self._normalize_source(source)

        # Target directory = repo name (without .git)
        repo_name = Path(repo_url.rstrip("/").split("/")[-1]).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        
        target = dest / repo_name

        if target.exists() and any(target.iterdir()):
            raise RuntimeError(f"Destination '{target}' already exists and is not empty.")
        logger.debug(f"The target directory is {target}")

        # ---- Build clone command ----        
        
        cmd = [self.git, "clone", "--depth", "1", "--no-tags"]
        
        if branch:
            logger.debug(f"Clone ref '{branch}'")
            cmd += ["-b", branch]

        cmd += [repo_url, str(target)]

        logger.debug(f"Run command --> {cmd}")
        try:
            subprocess.run(cmd, check=True)
        
        except FileNotFoundError as e:
            raise RuntimeError("git not found on PATH; install Git or set GIT_BINARY") from e
        except subprocess.CalledProcessError as e:
            sanitized = self._sanitize_userinfo_in_url(source)
            raise RuntimeError(f"git clone failed for source '{sanitized}': {e}") from e
        
        return target
        

    # ---------- helpers ----------

    def _validate_source_format(self, source: str) -> None:
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

        
    def _normalize_source(self, src: str) -> str:
        """Normalize GitLab-style shorthand to a full URL, configurable via env:
        ARTIFETCH_GIT_HOST   (default: gitlab.com)
        ARTIFETCH_GIT_PROTO  (ssh / https, default: ssh)
        ARTIFETCH_GIT_USER   (for ssh user, default: git)
        """
        if src.startswith(("http://", "https://", "git@", "ssh://")):
            return src
        host = os.getenv("ARTIFETCH_GIT_HOST", "gitlab.com")
        proto = os.getenv("ARTIFETCH_GIT_PROTO", "ssh").lower()
        if proto == "https":
            return f"https://{host}/{src}.git"
        user = os.getenv("ARTIFETCH_GIT_USER", "git")
        return f"{user}@{host}:{src}.git"


    @staticmethod
    def _sanitize_userinfo_in_url(source: str) -> str:
        """
        Redacts credentials in URL forms:
        - http://user[:pass]@host/...
        - https://user[:pass]@host/...
        - ssh://user@host/...
        Leaves SCP-style forms (git@host:org/repo.git) unchanged.

        Examples:
        https://user:token@github.com/org/repo.git -> https://***@github.com/org/repo.git
        https://user@domain:token@github.com/org/repo.git -> https://***@github.com/org/repo.git
        ssh://git@github.com/org/repo.git -> ssh://***@github.com/org/repo.git
        """
        # Replace one-or-more userinfo segments ending with '@' up to the host, keeping only '***@'.
        pattern = re.compile(r'^(?P<scheme>(?:https?|ssh))://(?:[^/@]+@)+', flags=re.IGNORECASE)
        return pattern.sub(r'\g<scheme>://***@', source)

