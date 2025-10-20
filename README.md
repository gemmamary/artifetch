# Artifetch

Artifetch is a universal artifact fetcher for developers, testers and CI/CD systems.

It can:
- Download artifacts from Artifactory
- Download job artifacts from GitLab
- Clone Git repositories

Artifetch works both as:
- A **Python library** (`from artifetch import fetch`)
- A **CLI tool** (`artifetch gitlab://...`)

Project goals:
- Minimal dependencies
- Safe and robust downloads
- Fallback to pure Python if official tools aren’t installed


## Usage 

Through commands

```shell
artifetch https://mycompany.jfrog.io/artifactory/libs-release/com/example/file.zip -p artifactory -d downloads/
```
or
```shell
artifetch libs-release/com/example/file.zip
```

In python code
```python
from artifetch.core import fetch

fetch("libs-release/com/example/file.zip", dest="downloads", provider="artifactory")
```
Set env variables:
```json
GITLAB_URL
GITLAB_TOKEN or CI_JOB_TOKEN

GIT_BINARY

ARTIFACTORY_URL
ARTIFACTORY_USER
ARTIFACTORY_TOKEN or ARTIFACTORY_PASSWORD
```

