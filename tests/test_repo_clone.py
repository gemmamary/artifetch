import os
import re
from pathlib import Path, PurePath
from types import SimpleNamespace
import pytest

from artifetch.fetchers.repo_clone import RepoCloneFetcher


# ----------------------------
# Helpers & fixtures
# ----------------------------

@pytest.fixture(autouse=True)
def clean_git_env(monkeypatch, tmp_path):
    """
    Ensure tests are deterministic:
    - Prevent python-dotenv from populating os.environ.
    - Remove host/proto/user overrides from the environment.
    - Work in a temp CWD so no project .env is discovered implicitly.
    """
    # Disable load_dotenv inside RepoCloneFetcher
    import artifetch.fetchers.repo_clone as gitmod
    monkeypatch.setattr(gitmod, "load_dotenv", lambda: None)

    # Remove potentially set envs
    for var in ("GIT_BINARY", "ARTIFETCH_GIT_HOST", "ARTIFETCH_GIT_PROTO", "ARTIFETCH_GIT_USER"):
        monkeypatch.delenv(var, raising=False)

    # Avoid picking up a .env in the repo root via working directory heuristics
    monkeypatch.chdir(tmp_path)


class GitRunDouble:
    """
    Test double for subprocess.run:
    - Records all calls.
    - Creates clone target directory when 'clone' is invoked (emulates Git creating the repo dir).
    - Can be configured to raise for specific commands.
    """
    def __init__(self, base_tmp: Path):
        self.base_tmp = base_tmp
        self.calls = []
        self.raise_on = None  # "clone" / predicate(argv)->bool
        self.capture_kwargs = []

    def __call__(self, args, check=True, **kwargs):
        argv = list(args)
        self.calls.append(argv)
        self.capture_kwargs.append(kwargs)

        # Raise if configured
        if self.raise_on:
            if callable(self.raise_on) and self.raise_on(argv):
                raise self._make_error(argv)
            if isinstance(self.raise_on, str) and self.raise_on in argv:
                raise self._make_error(argv)

        # Emulate 'git clone' creating the target dir (last arg)
        if "clone" in argv:
            target = Path(argv[-1])
            target.mkdir(parents=True, exist_ok=True)

        return SimpleNamespace(returncode=0, stdout="", stderr="")

    @staticmethod
    def _make_error(argv):
        import subprocess as _sp
        return _sp.CalledProcessError(128, argv, output="", stderr="mock error")


@pytest.fixture()
def git_double(tmp_path, monkeypatch):
    double = GitRunDouble(tmp_path)
    monkeypatch.setattr("subprocess.run", double)
    return double


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("GIT_BINARY", "ARTIFETCH_GIT_HOST", "ARTIFETCH_GIT_PROTO", "ARTIFETCH_GIT_USER"):
        monkeypatch.delenv(var, raising=False)


# ----------------------------
# URL builders for scenarios
# ----------------------------

PUBLIC_HOST = "gitlab.com"
PRIVATE_HOST = "git.private.example"
ORG = "org"
REPO = "monorepo"
NS_REPO = f"{ORG}/{REPO}"


def make_src_url(host: str, form: str) -> str:
    """
    Build a source URL for the main matrix:
      - https_dotgit:             https://<host>/<org>/<repo>.git
      - https_nodot:              https://<host>/<org>/<repo>
      - ssh_scp:                  git@<host>:<org>/<repo>.git
      - https_creds:              https://user:token@<host>/<org>/<repo>.git
      - https_dotgit_trailing:    https://<host>/<org>/<repo>.git/
      - https_nodot_trailing:     https://<host>/<org>/<repo>/
      - ssh_scheme_port:          ssh://git@<host>:2222/<org>/<repo>.git
    """
    if form == "https_dotgit":
        return f"https://{host}/{NS_REPO}.git"
    if form == "https_nodot":
        return f"https://{host}/{NS_REPO}"
    if form == "ssh_scp":
        return f"git@{host}:{NS_REPO}.git"
    if form == "https_creds":
        return f"https://user:token@{host}/{NS_REPO}.git"
    if form == "https_dotgit_trailing":
        return f"https://{host}/{NS_REPO}.git/"
    if form == "https_nodot_trailing":
        return f"https://{host}/{NS_REPO}/"
    if form == "ssh_scheme_port":
        return f"ssh://git@{host}:2222/{NS_REPO}.git"
    raise ValueError(form)


# ----------------------------
# Core matrix: host x url_form x branch_flag
# ----------------------------

HOST_CASES = [("public", PUBLIC_HOST), ("private", PRIVATE_HOST)]
URL_FORMS = [
    "https_dotgit",
    "https_nodot",
    "ssh_scp",
    "https_creds",
    "https_dotgit_trailing",
    "https_nodot_trailing",
    "ssh_scheme_port",
]
BRANCH_CASES = [None, "release/1.0"]

@pytest.mark.parametrize("host_label,host", HOST_CASES)
@pytest.mark.parametrize("url_form", URL_FORMS)
@pytest.mark.parametrize("branch", BRANCH_CASES)
def test_clone_matrix_all_requirements_and_existing_features(tmp_path, git_double, host_label, host, url_form, branch):
    """
    Covers:
      1) default branch clone and 2) specific branch clone
      3) public & private hosts
      4) URL forms (https .git / no .git / ssh scp) and 5) https creds
      PLUS: trailing slashes, ssh:// scheme with port
    """
    # Use a destination path with a space to verify arg handling
    dest = tmp_path / "with space" / "repos"
    dest.mkdir(parents=True, exist_ok=True)

    src = make_src_url(host, url_form)
    fetcher = RepoCloneFetcher()

    result = fetcher.fetch(src, dest, branch=branch)

    # Returned path: <dest>/<repo>
    assert result == dest / REPO
    assert result.exists()

    # Command basics
    assert git_double.calls, "No git command recorded"
    clone_call = git_double.calls[0]
    
    binname = PurePath(clone_call[0]).name.lower()
    assert binname in ("git", "git.exe", "git.cmd", "git.bat")  # git binary
    assert clone_call[1] == "clone"
    assert "--depth" in clone_call and "1" in clone_call
    assert "--no-tags" in clone_call

    if branch is None:
        assert "-b" not in clone_call
    else:
        assert "-b" in clone_call and branch in clone_call

    # Remote URL present; last argument is target path (may include a space)
    assert any(arg == src for arg in clone_call), f"Expected clone URL {src} in {clone_call}"
    assert clone_call[-1] == str(result)


# ----------------------------
# Errors & edge cases
# ----------------------------

def test_existing_nonempty_target_repo_raises(tmp_path, git_double):
    dest = tmp_path / "repos"
    repo_dir = dest / "monorepo"
    dest.mkdir()
    repo_dir.mkdir(parents=True)
    (repo_dir / "dummy.txt").write_text("x")

    f = RepoCloneFetcher()
    with pytest.raises(RuntimeError) as ei:
        f.fetch(f"https://{PUBLIC_HOST}/{NS_REPO}.git", dest)
    assert "already exists and is not empty" in str(ei.value)


def test_precreated_empty_target_dir_is_allowed(tmp_path, git_double):
    """
    If <dest>/<repo> exists but is empty, clone should proceed.
    """
    dest = tmp_path / "repos"
    target = dest / REPO
    target.mkdir(parents=True)  # empty
    f = RepoCloneFetcher()

    result = f.fetch(f"https://{PUBLIC_HOST}/{NS_REPO}.git", dest)
    assert result == target
    assert result.exists()


def test_calledprocesserror_is_wrapped_with_sanitized_url(tmp_path, monkeypatch):
    """
    When git fails, error message must include a sanitized URL prefix (***@).
    """
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    # Prepare a double that raises on 'clone'
    def _raise_on_clone(argv):
        return "clone" in argv
    double = GitRunDouble(tmp_path)
    double.raise_on = _raise_on_clone
    monkeypatch.setattr("subprocess.run", double)

    # Credentials to trigger sanitizer
    src = f"https://user:token@{PUBLIC_HOST}/{NS_REPO}.git"

    with pytest.raises(RuntimeError) as ei:
        f.fetch(src, dest)

    msg = str(ei.value)
    assert re.search(r"https?://\*{3}@", msg), msg  # redacted userinfo marker


def test_git_not_found_raises_clear_error(tmp_path, monkeypatch):
    """
    Simulate missing git binary (FileNotFoundError).
    """
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr("subprocess.run", _raise_file_not_found)

    with pytest.raises(RuntimeError) as ei:
        f.fetch(f"https://{PUBLIC_HOST}/{NS_REPO}.git", dest)
    assert "git not found on PATH" in str(ei.value)


@pytest.mark.parametrize("bad", ["ftp://x/y/z", "file:///tmp/x", "s3://bucket/repo", "data://blob"])
def test_unsupported_schemes_raise_value_error(tmp_path, bad):
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    with pytest.raises(ValueError):
        f.fetch(bad, dest)


def test_honors_custom_git_binary_from_env(tmp_path, git_double, monkeypatch):
    monkeypatch.setenv("GIT_BINARY", "/opt/custom/git")
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    f.fetch(f"https://{PUBLIC_HOST}/{NS_REPO}.git", dest)
    clone_call = git_double.calls[0]
    assert clone_call[0] == "/opt/custom/git"


# ----------------------------
# Shorthand normalization via env 
# ----------------------------

def test_shorthand_normalizes_to_ssh_by_default(tmp_path, git_double):
    """
    Default behavior: PROTO=ssh, USER=git, HOST=gitlab.com
    => clone URL should look like: git@gitlab.com:group/monorepo.git
    """
    src = "group/monorepo"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    f.fetch(src, dest)
    clone_call = git_double.calls[0]
    assert any(
        arg.startswith("git@gitlab.com:group/monorepo.git") for arg in clone_call
    ), f"Unexpected clone args: {clone_call}"


def test_shorthand_normalizes_to_https_when_env_set(tmp_path, git_double, monkeypatch):
    monkeypatch.setenv("ARTIFETCH_GIT_PROTO", "https")
    monkeypatch.setenv("ARTIFETCH_GIT_HOST", "git.mycorp.local")

    src = "group/sub/monorepo"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    f.fetch(src, dest)
    clone_call = git_double.calls[0]
    assert any(
        arg.startswith("https://git.mycorp.local/group/sub/monorepo.git")
        for arg in clone_call
    ), f"Unexpected clone args: {clone_call}"


def test_shorthand_normalizes_to_custom_ssh_user(tmp_path, git_double, monkeypatch):
    monkeypatch.setenv("ARTIFETCH_GIT_USER", "gitlab")
    src = "group/repo"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = RepoCloneFetcher()

    f.fetch(src, dest)
    clone_call = git_double.calls[0]
    assert any(
        arg.startswith("gitlab@gitlab.com:group/repo.git") for arg in clone_call
    ), f"Unexpected clone args: {clone_call}"