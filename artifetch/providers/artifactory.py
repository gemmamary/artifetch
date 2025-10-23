import os
from pathlib import Path
import requests
from dotenv import load_dotenv

from artifetch.utils.filesystem import ensure_dir


class ArtifactoryFetcher:
    """
    Fetcher for downloading artifacts from JFrog Artifactory.

    Authentication:
        - ARTIFACTORY_USER and ARTIFACTORY_TOKEN (or PASSWORD)
        - Optionally ARTIFACTORY_URL if you use relative paths
    """

    def __init__(self):
        # Load environment variables (if .env exists)
        load_dotenv()

        self.base_url = os.getenv("ARTIFACTORY_URL", "").rstrip("/")
        self.user = os.getenv("ARTIFACTORY_USER")
        self.token = os.getenv("ARTIFACTORY_TOKEN") or os.getenv("ARTIFACTORY_PASSWORD")

        if not self.user or not self.token:
            raise ValueError(
                "Artifactory credentials missing. Set ARTIFACTORY_USER and ARTIFACTORY_TOKEN."
            )

    def fetch(self, source: str, dest: Path) -> Path:
        """
        Download a file or folder from Artifactory.

        Args:
            source: Full Artifactory URL or repo-relative path.
            dest: Destination folder.

        Returns:
            Path to the downloaded file.
        """
        # Resolve destination path
        dest = Path(dest).resolve()
        ensure_dir(dest)

        # Build full URL
        url = source if source.startswith("http") else f"{self.base_url}/{source.lstrip('/')}"
        filename = Path(url).name
        file_path = dest / filename

        print(f"Downloading from Artifactory: {url}")

        try:
            response = requests.get(url, auth=(self.user, self.token), stream=True, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to download from Artifactory: {e}")

        # Save to disk
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"Downloaded to {file_path}")
        return file_path
