"""Core logic for routing URIs to providers."""

from artifetch.providers import artifactory, gitlab, git

PROVIDERS = {
    "artifactory": artifactory.ArtifactoryProvider(),
    "gitlab": gitlab.GitLabProvider(),
    "git": git.GitProvider(),
}

def fetch(uri: str, dest: str = ".", **kwargs):
    """Unified entry point for all downloads."""
    # TODO: parse scheme and delegate to correct provider
    pass