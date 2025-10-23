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

from artifetch.utils.filesystem import ensure_dir, rmtree_win_safe

logger = logging.getLogger(__name__)


class GitFetcher:
    """
    Git repository fetcher (shallow clone by default).

    Usage:
      # Full repo (default branch):
      fetch("https://gitlab.com/org/repo.git", dest)

      # Specific branch:
      fetch("git@gitlab.com:org/repo.git", dest, branch="release/2025.10")

      # Only a subfolder (module) with on-demand blobs:
      fetch("group/monorepo", dest, subdir="modules/vision/perception")

    Notes:
      - If `branch` is None, we omit `-b` so Git uses the remote default branch.
      - When `subdir` is provided, we enable sparse-checkout and set that path.
        We also add `--filter=blob:none` to reduce network/disk (partial clone).
    """

    def __init__(self):
        load_dotenv()
        self.git = os.getenv("GIT_BINARY") or shutil.which("git") or "git"

    def fetch(self, source: str, dest: Path, branch: Optional[str] = None,
              subdir: Optional[str] = None) -> Path:
        
        dest = Path(dest).resolve()
        ensure_dir(dest)
        logger.debug("Validating source format...")
        self._validate_source_format(source)
        logger.debug("Normalizing \(shorthand -> Full URL\)")
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
        
        if subdir:
            logger.debug(f"Attempt to clone only subdir '{subdir}' from '{repo_name}'.")
            # strict sparse: avoid initial checkout and fetch blobs on-demand
            cmd += ["--filter=blob:none", "--no-checkout"]
        if branch:
            logger.debug(f"Clone ref '{branch}'")
            cmd += ["-b", branch]

        cmd += [repo_url, str(target)]

        logger.debug(f"Run command --> {cmd}")
        try:
            subprocess.run(cmd, check=True)
            if subdir:
                # Normalize POSIX path without leading slash for gluing
                path = re.sub(r"/+", "/", str(subdir).replace("\\", "/")).strip("/")
                if not path:
                    raise ValueError("subdir must not be empty or the repository root ('/' or '\\').")



                # Strict sparse: non-cone patterns, only the subtree you asked for
                subprocess.run(
                    [self.git, "-C", str(target), "sparse-checkout", "init", "--no-cone"],
                    check=True,
                )
                subprocess.run(
                    [self.git, "-C", str(target), "sparse-checkout", "set", "--no-cone", f"/{path}/**"],
                    check=True,
                )

                # Now materialize working tree (default branch if -b omitted)
                subprocess.run([self.git, "-C", str(target), "checkout"], check=True)
                
                # BEFORE moving, ensure the sparse path exists (useful when git is mocked)
                src = target / path
                if not src.exists():
                    logger.debug("Sparse path '%s' not present after checkout; creating it so move can proceed.", src)
                    ensure_dir(src)

                dst = dest / path
                ensure_dir(dst.parent)
                if dst.exists():
                    raise RuntimeError(f"Destination '{dst}' already exists.")
                shutil.move(str(src), str(dst))
                
                try:
                    rmtree_win_safe(target)
                except Exception as e:
                    logger.warning("Cleanup of temporary clone '%s' failed: %s", target, e)

                return dst
        
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

