# Artifetch

**Artifetch** is a universal artifact fetcher. In **v1**, it focuses on **Git** repositories with:

- Fast **shallow clones** by default
- Optional **branch/tag checkout**
- Support for HTTPS, SSH, and **GitLab-style shorthand** (`group/repo` → full URL)

---

## Features

- **Git provider**:
  - Shallow clone (`--depth 1`, `--no-tags`)
  - Branch/tag selection via `--branch/-b`

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

# Clone and checkout to a specific branch
artifetch https://gitlab.com/org/monorepo.git -d ./repos -p git -b release/1.0 


```

Options:

- `source`: Git URL or shorthand
- `--dest, -d`: Destination folder (default: `.`)
- `--branch, -b`: Branch or tag
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

```

### Direct Git provider

```Python
from pathlib import Path
from artifetch.providers.git import GitFetcher

f = GitFetcher()
dest = Path("./workspace")

# SSH URL
p = f.fetch("git@gitlab.com:org/monorepo.git", dest, branch="main")

# HTTPS
p = f.fetch("https://gitlab.com/org/monorepo.git", dest)

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

- **Destination rules**:
  - Full repo → `dest/<repo_name>`

---

## Troubleshooting

- **git not found**: Install Git or set `GIT_BINARY`.
- **Destination exists**: Remove or rename before retry.

---

## Roadmap

- GitLab artifacts
- Artifactory downloads
- Repository Content

--- 

## License

MIT
