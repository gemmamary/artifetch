from pathlib import Path
from typing import Optional, Protocol, Dict, Any, Type, cast
import sys, logging

from artifetch.providers.artifactory import ArtifactoryFetcher
from artifetch.providers.gitlab import GitLabFetcher
from artifetch.providers.git import GitFetcher

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when fetching an artifact fails."""


class Fetcher(Protocol):
    """Common interface for all fetchers."""
    def fetch(self, source: str, dest: Path) -> Path: ...


# Registry of available fetchers
FETCHERS: Dict[str, Any] = {
    "artifactory": ArtifactoryFetcher,
    "gitlab": GitLabFetcher,
    "git": GitFetcher,
}


def fetch(
    source: str,
    dest: Optional[str] = None,
    provider: Optional[str] = None,
    *,
    branch: Optional[str] = None,
    subdir: Optional[str] = None,
) -> Path:
    """
    Fetch an artifact or repository from a supported provider.

    Args:
        source: The URL or identifier of the resource.
        dest: Local destination path. Defaults to current directory.
        provider: Explicit provider key ('gitlab', 'artifactory', 'git').
        branch: (git only) optional branch/tag/ref. If None, Git uses the remote's default branch.
        subdir: (git only) optional subdirectory to materialize via sparse-checkout.

    Returns:
        Path to the downloaded artifact or repo.
        Note: for git with `subdir`, returns the subfolder path within the repo.
    """
    dest_path = Path(dest or ".").resolve()

    # Auto-detect provider if not specified; normalize case
    if provider:
        logging.debug(f"Provider set by the user.")
    else:
        logging.debug("Detecting provider...")
    provider = (provider or detect_provider(source)).lower()
    logging.debug(f"Fetching artifacts from: {provider}")
    if provider not in FETCHERS:
        logging.error(f"Failed to fetch artifact since {provider} is not yet supported.")
        raise FetchError(f"Unsupported provider: {provider}")
    

    fetcher_cls: Type = FETCHERS[provider]
    fetcher = fetcher_cls()

    try:
        if provider == "git":
            git_fetcher = cast(GitFetcher, fetcher)
            result = git_fetcher.fetch(source, dest_path, branch=branch, subdir=subdir)
        else:
            result = fetcher.fetch(source, dest_path)

        logger.info(f"Successfully fetched via {provider}: {result}")
        return result
    except Exception as e:
        logger.error(f"Fetch failed: %s", e)
        raise FetchError(str(e)) from e


def detect_provider(source: str) -> str:
    """
    Try to detect the provider from the source string.
    - Prefer 'git' if the string clearly looks like a Git repo or Git shorthand.
    - Prefer explicit host hints for Artifactory and GitLab artifact URLs.
    """
    s = source.strip()
    lower = s.lower()

    # Explicit hosts first
    if "artifactory" in lower:
        return "artifactory"
    # If it's a GitLab artifact/API link (non-.git), route to GitLab provider
    if "gitlab" in lower and not s.endswith(".git"):
        return "gitlab"

    # Git signals
    if s.endswith(".git"):
        return "git"
    if s.startswith(("git@", "ssh://")):
        return "git"
    if s.startswith(("http://", "https://")):
        known_git_hosts = ("github.com", "gitlab.com", "bitbucket.org")
        if any(h in lower for h in known_git_hosts) or s.endswith(".git"):
            return "git"

    # Git shorthand (group[/sub]/repo)
    if "/" in s and " " not in s and "@" not in s and ":" not in s:
        return "git"

    # Fallback
    raise ValueError("Couldn't auto detect provider based on URL. Please specify provider and try again.")