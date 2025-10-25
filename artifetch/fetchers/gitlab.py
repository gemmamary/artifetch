from __future__ import annotations
import os, gitlab
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse
from dotenv import load_dotenv
from artifetch.utils.filesystem import ensure_dir


class GitLabFetcher:
    """
    Fetcher for GitLab job artifacts.

    Environment:
      - GITLAB_URL (required unless you pass a full https URL as source)
      - GITLAB_TOKEN (personal access token or CI_JOB_TOKEN in CI)

    Supported source formats:
      1) Full URL to artifacts, e.g.
         https://gitlab.example.com/group/project/-/jobs/123/artifacts/download

         (or .../artifacts.zip — GitLab redirects these to the same endpoint)

      2) Shorthand path relative to server:
         group/project/-/jobs/123/artifacts.zip
    """

    def __init__(self):
        load_dotenv()
        self.url = os.getenv("GITLAB_URL", "").rstrip("/")
        self.token = os.getenv("GITLAB_TOKEN") or os.getenv("CI_JOB_TOKEN")

        if not self.token:
            raise ValueError("GitLab token missing. Set GITLAB_TOKEN or CI_JOB_TOKEN.")

    def fetch(self, source: str, dest: Path) -> Path:
        dest = Path(dest).resolve()
        ensure_dir(dest)

        is_full_url = source.startswith("http://") or source.startswith("https://")
        project_path, job_id = (
            self._parse_full_url(source) if is_full_url else self._parse_shorthand(source)
        )

        server = self._server_from_source(source) if is_full_url else self.url
        if not server:
            raise ValueError("GITLAB_URL must be set for shorthand sources.")

        gl = gitlab.Gitlab(server, private_token=self.token, timeout=60)
        project = gl.projects.get(project_path)
        job = project.jobs.get(job_id)

        out_file = dest / f"{project_path.replace('/', '_')}_job{job_id}.zip"
        with open(out_file, "wb") as f:
            # python-gitlab streams the artifacts into the given writer via `action`
            job.artifacts(streamed=True, action=f.write)

        return out_file

    # ---------- helpers ----------

    def _server_from_source(self, source: str) -> str:
        parsed = urlparse(source)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _parse_full_url(self, url: str) -> Tuple[str, int]:
        """
        Extract project path and job id from a full GitLab URL.
        Works for:
          .../<group>/<project>/-/jobs/<job_id>/artifacts.zip
          .../<group>/<project>/-/jobs/<job_id>/artifacts/download
        """
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]

        # Find '/-/jobs/<id>/...'
        try:
            dash_idx = parts.index("-")
            if parts[dash_idx + 1] != "jobs":
                raise ValueError
            job_id = int(parts[dash_idx + 2])
        except Exception as e:
            raise ValueError(f"Unsupported GitLab artifacts URL format: {url}") from e

        project_path = "/".join(parts[:dash_idx])
        return project_path, job_id

    def _parse_shorthand(self, path: str) -> Tuple[str, int]:
        """
        Parse 'group/project/-/jobs/<id>/artifacts(.zip|/download)'
        """
        parts = [p for p in path.split("/") if p]
        try:
            dash_idx = parts.index("-")
            if parts[dash_idx + 1] != "jobs":
                raise ValueError
            job_id = int(parts[dash_idx + 2])
        except Exception as e:
            raise ValueError(
                "Unsupported GitLab shorthand path. "
                "Expected: group/project/-/jobs/<id>/artifacts.zip"
            ) from e

        project_path = "/".join(parts[:dash_idx])
        return project_path, job_id