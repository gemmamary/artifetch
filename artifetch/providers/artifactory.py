"""Download artifacts from Artifactory."""

class ArtifactoryProvider:
    def __init__(self):
        """Initialize provider (read env vars, tokens, etc)."""
        pass

    def fetch(self, path: str, dest: str = ".", **kwargs):
        """Download a file or folder from Artifactory."""
        pass