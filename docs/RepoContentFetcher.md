RepoContentFetcher (GitLab) 
================================================

## Overview
--------
`RepoContentFetcher` downloads repository content (entire repo, a
flattened subfolder, or a single file) from GitLab using only HTTPS calls to the
GitLab REST API. It supports both a concise `gitlab://` grammar and real GitLab
web URLs (prefixed with `gitlab://`). It streams archives/files efficiently and
requires no local `git` binary.

## What it can do
--------------
- **Download an entire repository** as a ZIP archive and extract it.
- **Download a subfolder** pre-trimmed server-side and **flatten** it on extract
  (`path/to/dir/a/b.txt` → `a/b.txt`).
- **Download a single file** via the `raw` file endpoint.
- **Target a specific ref** (branch, tag, or SHA) for all operations.


## Supported input formats
-----------------------
### New compact grammar (recommended)
```
# Basic forms (ref defaults to HEAD)
gitlab://<namespace>/<repo>

# With ref
gitlab://<namespace>/<repo>@<ref>

# Subfolder (flattened) at a ref
gitlab://<namespace>/<repo>@<ref>//<path/to/dir>

# Single file at a ref
gitlab://<namespace>/<repo>@<ref>//<path/to/file.ext>
```

### Real GitLab web URLs (convenience)
Prefix the normal GitLab URL with `gitlab://` and the fetcher will derive the API base:
```
# Root of repo (ref = HEAD)
gitlab://https://gitlab.example.com/group/repo

# Subfolder
gitlab://https://gitlab.example.com/group/repo/-/tree/<ref>/<path/to/dir>

# Single file
gitlab://https://gitlab.example.com/group/repo/-/blob/<ref>/<path/to/file.ext>
```

## Authentication
--------------
If `GITLAB_TOKEN` is set, it is sent as the `PRIVATE-TOKEN` header.

## Discovering your GitLab API base
--------------------------------
The API base is resolved in this order:
1. `ARTIFETCH_GITLAB_API_BASE` (used **as-is**)
2. `ARTIFETCH_GIT_HOST` with scheme → append `/api/v4`
3. `ARTIFETCH_GIT_HOST` without scheme → assume `https://` and append `/api/v4`
4. Fallback to `https://gitlab.com/api/v4`

## Conflict/overwrite behavior
---------------------------
- **Single file fetch** writes to `dest/<filename>` and **overwrites** any existing
  file with the same name.
- **Repo/subfolder fetch** extracts into `dest`, overwriting any existing files at
  those relative paths. Subfolder content is flattened (top-level subfolder is
  removed).

## Usage examples
--------------

### Repo content via CLI (full repo)
```
artifetch "gitlab://group/project@main" --dest ./out-full
```

### Repo content via CLI (subfolder flattened)
```
artifetch "gitlab://group/project@main//docs" --dest ./out-docs
```

### Repo content via CLI (single file)
```
artifetch "gitlab://group/project@main//README.md" --dest ./out-file
```

### Download repository content (full repo snapshot without `.git`)
------------------------------------------------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_content import RepoContentFetcher

fetcher = RepoContentFetcher()
fetcher.fetch("gitlab://group/project@main", Path("./out-full"), kind="repo")
```

### Download a subfolder (flattened into destination)
----------------------------------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_content import RepoContentFetcher

fetcher = RepoContentFetcher()
# Only the contents of docs/ appear directly in ./out-docs (no parent folders)
fetcher.fetch("gitlab://group/project@main//docs", Path("./out-docs"), kind="dir")
```

### Download a single file
-------------------------
```python
from pathlib import Path
from artifetch.fetchers.repo_content import RepoContentFetcher

fetcher = RepoContentFetcher()
# Saves README.md directly into ./out-file
fetcher.fetch("gitlab://group/project@main//README.md", Path("./out-file"), kind="file")
```

### Other scenarios

```python
from pathlib import Path
from repo_content import RepoContentFetcher

fetcher = RepoContentFetcher()

# 1) Whole repository (default branch)
fetcher.fetch('gitlab://group/sub/repo', Path('out'), kind='repo')

# 2) Subfolder (flattened), specific branch
fetcher.fetch('gitlab://group/repo@main//services/auth', Path('auth_out'), kind='dir')

# 3) Single file from a tag
fetcher.fetch('gitlab://group/repo@v1.2.3//CHANGELOG.md', Path('here'))

# 4) Using a full web URL (self-hosted)
fetcher.fetch('gitlab://https://gitlab.company.com/team/repo/-/tree/dev/tools', Path('tools'))
```

Notes & caveats
---------------
- A path like `folder.with.dots` is heuristically treated as a **file** (because it
  has an extension). If you actually want a **directory** with dots in its name,
  pass `kind='dir'` explicitly.
- For safety, ensure destination paths are trustworthy. The extractor strips the
  archive's top folder and optionally the requested subfolder, then writes to `dest`.

Running the tests
-----------------
This project uses `pytest`. Install dev deps and run:
```
pip install -U pytest
pytest -q
```

