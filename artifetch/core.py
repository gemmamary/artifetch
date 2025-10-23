# artifetch/core.py

from pathlib import Path
from typing import Optional, Protocol, Dict, Type
import sys

from artifetch.providers.artifactory import ArtifactoryFetcher
from artifetch.providers.gitlab import GitLabFetcher
from artifetch.providers.git import GitFetcher

class FetchError(Exception):
    """Raised when fetching an artifact fails."""


class Fetcher(Protocol):
    """Common interface for all fetchers."""

    def fetch(self, source: str, dest: Path) -> Path:
        ...


# Registry of available fetchers
FETCHERS: Dict[str, Type[Fetcher]] = {
    "artifactory": ArtifactoryFetcher,
    "gitlab": GitLabFetcher,
    "git": GitFetcher,
}


def fetch(source: str, dest: Optional[str] = None, provider: Optional[str] = None) -> Path:
    """
    Fetch an artifact or repository from a supported provider.

    Args:
        source: The URL or identifier of the resource.
        dest: Local destination path. Defaults to current directory.
        provider: Explicit provider key ('gitlab', 'artifactory', 'git').

    Returns:
        Path to the downloaded artifact.
    """
    dest_path = Path(dest or ".").resolve()

    # Auto-detect provider if not specified
    provider = provider or detect_provider(source)
    if provider not in FETCHERS:
        raise FetchError(f"Unsupported provider: {provider}")

    fetcher_cls = FETCHERS[provider]
    fetcher = fetcher_cls()

    try:
        result = fetcher.fetch(source, dest_path)
        print(f"Successfully fetched via {provider}: {result}")
        return result
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        raise FetchError(str(e))


def detect_provider(source: str) -> str:
    """
    Try to detect the provider from the source string.
    """
    source = source.lower()
    if "gitlab" in source:
        return "gitlab"
    if "artifactory" in source:
        return "artifactory"
    if source.endswith(".git") or source.startswith("git@") or "github" in source:
        return "git"
    return "artifactory"  # default fallback
