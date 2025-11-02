RepoCloneFetcher – Usage Guide
==============================

Overview
--------
RepoCloneFetcher provides a simple way to clone Git repositories (shallow by default) using HTTPS or SSH.
Use this fetcher when you need the entire repository (including the .git metadata/history). If you only need the working-tree files without .git, use RepoContentFetcher instead.

Key capabilities:
- Full repository clone (remote default branch).
- Clone a specific branch or tag.
- GitLab-style shorthand support (e.g., "group/repo") that expands to a full SSH/HTTPS URL via env vars.
- Sensible error messages with credentials sanitized in URLs.


Installation & Prerequisites
----------------------------
- Python 3.10+ (or your project’s supported version).
- Git installed and available on your system PATH.

If your project uses a virtual environment:
```
    python -m venv .venv
    . .venv/bin/activate
    pip install .   
```

Environment Variables
---------------------
You can configure RepoCloneFetcher behavior using these variables:

1) GIT_BINARY
   Description : Absolute path to the git binary if it’s not on PATH.
   Default     : Auto-detect via shutil.which("git") or fall back to "git".

2) ARTIFETCH_GIT_HOST
   Description : Git host for shorthand normalization.
   Default     : gitlab.com

3) ARTIFETCH_GIT_PROTO
   Description : Protocol for shorthand; valid values: "ssh" or "https".
   Default     : ssh

4) ARTIFETCH_GIT_USER
   Description : SSH user for shorthand when ARTIFETCH_GIT_PROTO=ssh.
   Default     : git

Example .env:
-------------
```
ARTIFETCH_GIT_HOST=gitlab.com
ARTIFETCH_GIT_PROTO=https
# ARTIFETCH_GIT_USER is only used for SSH shorthand; ignored for https
GIT_BINARY=/usr/bin/git
```


Python API
----------
```
Module   : artifetch.fetchers.repo_clone
Class    : RepoCloneFetcher
Method   : fetch(source: str, dest: Path, branch: Optional[str] = None) -> Path
```

Behavior:
- If branch is None, RepoCloneFetcher omits "-b" so Git uses the remote’s default branch.
- The target directory will be "<dest>/<repo-name>" (stripping a trailing ".git" from the repo name).
- Clone options: shallow by default --depth=1 and --no-tags.

Usage Examples:
---------------
From the top level API:
```python
from artifetch.core import fetch

# Clones default branch
fetch("https://gitlab.com/org/repo.git", "/tmp/repos", provider="repo_clone")
```

From the RepoCloneFetcher class:
```python
from artifetch.fetchers.repo_clone import RepoCloneFetcher

# Clones default branch
rover = RepoCloneFetcher()
rover.fetch("https://gitlab.com/org/repo.git", "/tmp/repos")
```

From a specific branch:
```python
from artifetch.core import fetch

# Clones from branch 'release/documentation'
fetch("https://gitlab.com/org/repo.git", "/tmp/repos", provider="repo_clone", branch="release/2025.10")
```

From a specific tag:
```python
from artifetch.core import fetch

# Clones from the version tagged 'v1.4.1'
fetch("https://gitlab.com/org/repo.git", "/tmp/repos", provider="repo_clone", branch="v1.4.1")
```

CLI usage:

```shell
# If your project provides a CLI wrapper, a typical command might look like
artifetch "git@gitlab.com:org/repo.git" --dest "/tmp/repos" --provider "repo_clone" --branch "feature/my_feature"
```
> Adjust flag names to your actual CLI. The Python API is authoritative; the CLI is just a thin wrapper.

Clone via SSH:
```python
from artifetch.core import fetch

fetch("git@gitlab.com:org/repo.git", "/tmp/repos", provider="repo_clone")
```

Clone using gitlab style shorthand:
```python

from artifetch.core import fetch

# Requires ARTIFETCH_GIT_HOST / ARTIFETCH_GIT_PROTO (and possibly ARTIFETCH_GIT_USER for ssh)
# If ARTIFETCH_GIT_PROTO=https  -> https://<host>/<group/repo>.git
# If ARTIFETCH_GIT_PROTO=ssh    -> <user>@<host>:<group/repo>.git
fetch("git@gitlab.com:org/repo.git", "/tmp/repos", provider="repo_clone")
```



Shorthand Normalization Rules
-----------------------------
If source starts with any of:
  - http://, https://, git@, ssh://
then RepoCloneFetcher uses the source as-is (no normalization).

If source looks like "namespace/repo" (contains a slash) and does NOT start with the above:
  - Fetch host = ARTIFETCH_GIT_HOST or "gitlab.com"
  - If ARTIFETCH_GIT_PROTO=https:
        normalized URL = https://<host>/<namespace/repo>.git
  - Else (ssh):
        user = ARTIFETCH_GIT_USER or "git"
        normalized URL = <user>@<host>:<namespace/repo>.git


Destination Rules
-----------------
- The effective target path is: <dest>/<repo-name>, where repo-name is derived from the source URL
  (a trailing ".git" is stripped).
- If the target directory already exists and is not empty, RepoCloneFetcher raises a RuntimeError to
  avoid clobbering existing content.


Logging & Diagnostics
---------------------
- RepoCloneFetcher uses the `logging` module under the logger name of its module (e.g., __name__).
- Set log level to DEBUG to see normalization, validations, and the exact git command run.
  Example:
    import logging
    logging.basicConfig(level=logging.DEBUG)

- The executed command is approximately:
    [git, "clone", "--depth", "1", "--no-tags", ("-b", branch)?, repo_url, target_dir]


Error Handling
--------------
RepoCloneFetcher raises:
- ValueError:
    * Unsupported URL schemes such as ftp://, file://, s3://, data://
    * Source that is neither a valid URL/SCP nor a recognizable shorthand (namespace/repo)
- RuntimeError:
    * git binary not found on PATH (or GIT_BINARY invalid)
    * Destination already exists and is not empty
    * `git clone` exits with a non-zero status code (the error message will include a sanitized URL)

Credential Sanitization:
- Any http(s) or ssh URL with user info will be sanitized in error messages, for example:
    https://user:token@github.com/org/repo.git  ->  https://***@github.com/org/repo.git
    ssh://git@github.com/org/repo.git           ->  ssh://***@github.com/org/repo.git
- SCP-style forms like git@host:org/repo.git are left unchanged (they don’t embed passwords).


Troubleshooting
---------------
1) "git not found on PATH"
   - Ensure Git is installed and available on PATH.
   - Or set GIT_BINARY to the absolute path of the git executable.

2) "Invalid Git source format"
   - Check the URL scheme (http/https/ssh) or use a valid SCP form (git@host:org/repo.git).
   - For shorthand, ensure it looks like "namespace/repo" and that ARTIFETCH_GIT_HOST/PROTO are set correctly.

3) "Destination already exists"
   - Provide an empty/non-existing destination folder, or delete existing contents.

4) Clone fails (non-zero exit)
   - Verify you are using a valid clone URL
   - Verify network connectivity and credentials/SSH keys.
   - For private repos over HTTPS, ensure your credential helper or token is configured for Git.
   - For SSH, confirm your SSH agent/keys and known_hosts are set up.


Comparison: RepoCloneFetcher vs RepoContentFetcher
--------------------------------------------------
- RepoCloneFetcher: Uses `git clone` (shallow by default). Produces a full repository checkout with a `.git` directory.
- RepoContentFetcher: Downloads repository files (zip/raw APIs) without `.git`. No history; useful for quick, read-only content acquisition.

Choose:
- Use RepoCloneFetcher when you need Git operations (commits, branches, further pulls).
- Use RepoContentFetcher when you only need files and faster, no-Git downloads.


Security Notes
--------------
- Be careful when passing tokens in URLs (e.g., https://user:TOKEN@host/...).
- Although error messages sanitize credentials, avoid logging raw URLs with secrets.
- Prefer SSH with properly managed keys for private repositories if possible.


Quick End-to-End Example
------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_clone import RepoCloneFetcher

# Optionally load .env if python-dotenv is installed (RepoCloneFetcher calls load_dotenv() in __init__)
# .env can define ARTIFETCH_GIT_HOST, ARTIFETCH_GIT_PROTO, ARTIFETCH_GIT_USER, GIT_BINARY

fetcher = RepoCloneFetcher()

dest = Path("/tmp/repos")

# Public repository (HTTPS)
repo = fetcher.fetch("https://gitlab.com/org/repo.git", dest)
print("Cloned to:", repo)

# Private repository via SSH (branch)
repo = fetcher.fetch("git@gitlab.com:org/private-repo.git", dest, branch="main")
print("Cloned to:", repo)
```

Versioning & Maintenance
------------------------
- Shallow cloning flags (`--depth 1 --no-tags`) are set for performance; if you need full history or tags,
  consider extending RepoCloneFetcher to accept additional flags or perform a post-fetch unshallow.
- Keep your Git version updated to ensure compatibility with newer host features and protocols.
