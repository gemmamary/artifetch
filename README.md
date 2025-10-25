
Artifetch (High-Level README)
=============================

Overview
--------
Artifetch is a universal fetcher for developer assets. In v1 it focuses on Git-based workflows and related content.

The purpose of Artifetch
-----------------------
- Fetch full repositories via shallow Git clone (with optional branch/tag).
- Fetch repository content without Git (entire repo contents, a subfolder flattened into the destination, or a single file).
- Fetch build artifacts (e.g., GitLab job artifacts, Artifactory downloads).

Core Fetchers
-------------
- RepoCloneFetcher  (module: artifetch.fetchers.repo_clone)
  Shallow `git clone` by default, optional branch/tag checkout.
  See detailed guide: docs/RepoCloneFetcher.md

Installation
------------
From PyPI:
    pip install artifetch

From source:
    pip install -e .

High-Level Usage Examples
-------------------------
1) Clone a repository (default branch)
-------------------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_clone import RepoCloneFetcher

fetcher = RepoCloneFetcher()
target = fetcher.fetch("https://gitlab.com/org/repo.git", Path("./repos"))
print(f"Cloned to: {target}")
```

2) Clone a repository (specific branch)
--------------------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_clone import RepoCloneFetcher

fetcher = RepoCloneFetcher()
target = fetcher.fetch("git@gitlab.com:org/repo.git", Path("./repos"), branch="release/2025.10")
print(f"Cloned to: {target}")
```


CLI Usage
---------
Artifetch also includes a CLI for automation. Your command layout may vary depending on your integration.
Typical examples:

# Clone via CLI (default branch)
```
artifetch repo-clone --source "https://gitlab.com/org/repo.git" --dest ./repos
```

# Clone via CLI (specific branch)
```
artifetch repo-clone --source "git@gitlab.com:org/repo.git" --dest ./repos --branch main
```


Environment Variables
---------------------
Common variables (used by RepoCloneFetcher and/or RepoContentFetcher):

- GIT_BINARY              : Path to git executable (RepoCloneFetcher). Default: auto-detect via PATH.
- ARTIFETCH_GIT_HOST      : Host for shorthand normalization (RepoCloneFetcher). Default: gitlab.com
- ARTIFETCH_GIT_PROTO     : ssh or https for shorthand (RepoCloneFetcher). Default: ssh
- ARTIFETCH_GIT_USER      : SSH user for shorthand (RepoCloneFetcher). Default: git
- GITLAB_TOKEN            : Optional token for private GitLab when using RepoContentFetcher (and GitLabFetcher).
- ARTIFETCH_GITLAB_API_BASE: Optional explicit GitLab API base (e.g., https://git.example.local/api/v4)
- ARTIFETCH_GIT_HOST (same name, used by RepoContentFetcher env-discovery for GitLab host if needed)

Example (shell):
    export ARTIFETCH_GIT_PROTO=https
    export ARTIFETCH_GIT_HOST=git.mycorp.local

Or in a .env file:
    ARTIFETCH_GIT_PROTO=https
    ARTIFETCH_GIT_HOST=git.mycorp.local

Documentation
-------------
- docs/RepoCloneFetcher.md (detailed clone behavior, flags, troubleshooting)
- RepoContentFetcher (coming soon)
- GitLabFetcher (coming soon)
- ArtifactoryFetcher (coming soon)

Roadmap
-------
- RepoContentFetcher  (module: artifetch.fetchers.repo_content)
  Download repository files without `.git` (full repo snapshot, a subfolder flattened, or a single file).

- GitLabFetcher  (module: artifetch.fetchers.gitlab)
  Retrieve GitLab job artifacts.

- ArtifactoryFetcher  (module: artifetch.fetchers.artifactory)
  Download artifacts from Artifactory.

License
-------
MIT
