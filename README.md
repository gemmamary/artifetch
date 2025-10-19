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
