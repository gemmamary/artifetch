# Artifetch

**Artifetch** is a universal artifact fetcher. In **v1**, it focuses on **Git** repositories with:

- Fast **shallow clones** by default
- Optional **branch/tag checkout**
- **Sparse checkout of a subdirectory**, materialized **directly under your destination folder**
- Support for HTTPS, SSH, and **GitLab-style shorthand** (`group/repo` → full URL)
- Safe cleanup on Windows

---

## Features

- **Git provider**:
  - Shallow clone (`--depth 1`, `--no-tags`)
  - Branch/tag selection via `--branch/-b`
  - Sparse checkout for a single subdirectory
  - Credential redaction in error messages

---

## Installation

From PyPI:

```Shell
pip install artifetch
```

From source:

```Shell
pip install -e .
```

--- 

## CLI Usage

```Shell
# Clone default branch into ./repos/monorepo
artifetch https://gitlab.com/org/monorepo.git -d ./repos -p git

# Clone a specific branch
artifetch https://gitlab.com/org/monorepo.git -d ./repos -p git -b release/1.0 

# Materialize only a subdirectory directly under dest
artifetch group/monorepo -d ./workspace -p git -s modules/adas/camera  

# SSH URL with subdir
artifetch git@gitlab.com:org/monorepo.git -d ./workspace -p git -s modules/vision/perception 

# Subdirectory from a specific branch
artifetch group/monorepo -d ./workspace -p git -b release/1.0 -s modules/adas/camera

```

Options:

- `source`: Git URL or shorthand
- `--dest, -d`: Destination folder (default: `.`)
- `--branch, -b`: Branch or tag
- `--subdir, -s`: Subdirectory to materialize
- `--verbose, -v`: Enable debug logs

---

## Python API

### High-level helper

```Python
from pathlib import Path
from artifetch.core import fetch

dest = Path("./workspace")

# Full repo
path = fetch("https://gitlab.com/org/monorepo.git", dest=dest)
print(path)  # ./workspace/monorepo

# Branch
path = fetch("https://gitlab.com/org/monorepo.git", dest=dest, branch="release/1.0")

# Subdirectory only
path = fetch("group/monorepo", dest=dest, subdir="modules/adas/camera")
print(path)  # ./workspace/modules/adas/camera

```

### Direct Git provider

```Python
from pathlib import Path
from artifetch.providers.git import GitFetcher

f = GitFetcher()
dest = Path("./workspace")

# SSH URL
p = f.fetch("git@gitlab.com:org/monorepo.git", dest, branch="main")

# HTTPS + subdir
p = f.fetch("https://gitlab.com/org/monorepo.git", dest, subdir="modules/vision/perception")

```

---

## Environment Variables


|Variable|Purpose|Default|
|---|---|---|
|GIT_BINARY|Path to git executable|auto-detect|
|ARTIFETCH_GIT_HOST|Host for shorthand normalization|gitlab.com|
|ARTIFETCH_GIT_PROTO|ssh or https for shorthand|ssh|
|ARTIFETCH_GIT_USER|SSH user for shorthand|git|



Example:

shell:
```Shell
export ARTIFETCH_GIT_PROTO=https
export ARTIFETCH_GIT_HOST=git.mycorp.local
```
or .env file
```
ARTIFETCH_GIT_PROTO=https
ARTIFETCH_GIT_HOST=git.mycorp.local
```

---

## Behavior Details

- **Subdir normalization**: Converts backslashes to `/`, collapses `//`, trims leading/trailing slashes.
- **Destination rules**:
  - Full repo → `dest/<repo_name>`
  - Subdir → `dest/<normalized_subdir>`
- **Cleanup**: Repo folder is deleted after moving subdir (Windows-safe retry logic).

---

## Troubleshooting

- **Access denied on Windows**: Artifetch retries deletion with backoff and clears read-only bits.
- **git not found**: Install Git or set `GIT_BINARY`.
- **Destination exists**: Remove or rename before retry.

---

## Roadmap

- GitLab artifacts
- Artifactory support

--- 

## License

MIT
