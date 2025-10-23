import os
import re
from pathlib import Path
from types import SimpleNamespace
import pytest

from artifetch.providers.git import GitFetcher


# ----------------------------
# Helpers & fixtures
# ----------------------------

def _norm_subdir(s: str) -> Path:
    """Normalize subdir like the implementation (forward slashes, collapse //, strip leading/trailing /)."""
    s = re.sub(r"/+", "/", str(s).replace("\\", "/")).strip("/")
    if not s:
        # This mirrors the guard in your implementation when subdir is provided and normalizes to empty
        raise ValueError("subdir must not be empty or the repository root ('/' or '\\').")
    return Path(*s.split("/"))


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
        self.raise_on = None  # "clone" / "sparse-checkout" / "checkout" or a predicate(argv)->bool

    def __call__(self, args, check=True, **kwargs):
        argv = list(args)
        self.calls.append(argv)

        # Raise if configured
        if self.raise_on:
            if callable(self.raise_on) and self.raise_on(argv):
                raise self._make_error(argv)
            if isinstance(self.raise_on, str) and self.raise_on in argv:
                raise self._make_error(argv)

        # Emulate git clone creating the target dir (last arg)
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
# Core behavior
# ----------------------------

def test_fetch_no_subdir_default_branch(tmp_path, git_double):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    result = f.fetch(src, dest)

    # Returns dest/repo_name (created by the double)
    assert result == dest / "monorepo"
    assert result.exists()

    # Command composition
    clone_call = git_double.calls[0]
    assert clone_call[1] == "clone"
    assert "--depth" in clone_call and "1" in clone_call
    assert "--no-tags" in clone_call
    assert "--filter=blob:none" not in clone_call
    assert "--no-checkout" not in clone_call
    assert "-b" not in clone_call


def test_fetch_with_branch_no_subdir(tmp_path, git_double):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    result = f.fetch(src, dest, branch="release/1.0")

    assert result == dest / "monorepo"
    clone_call = git_double.calls[0]
    assert "-b" in clone_call and "release/1.0" in clone_call


def test_fetch_with_subdir_no_branch(tmp_path, git_double):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    subdir = "modules/adas/camera"
    expected = dest / _norm_subdir(subdir)

    result = f.fetch(src, dest, subdir=subdir)

    # Returns dest/<subdir> and repo folder removed
    assert result == expected
    assert expected.exists()
    assert not (dest / "monorepo").exists()

    # Sparse clone flags present; no -b
    clone_call = git_double.calls[0]
    assert "--filter=blob:none" in clone_call
    assert "--no-checkout" in clone_call
    assert "-b" not in clone_call

    # Subsequent sparse-checkout commands executed
    all_joined = [" ".join(c) for c in git_double.calls]
    assert any("sparse-checkout init --no-cone" in s for s in all_joined)
    assert any("sparse-checkout set --no-cone " in s for s in all_joined)
    assert any(" checkout" in s for s in all_joined)


def test_fetch_with_branch_and_subdir(tmp_path, git_double):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    subdir = "modules/vision/perception"
    expected = dest / _norm_subdir(subdir)

    result = f.fetch(src, dest, branch="release/1.0", subdir=subdir)
    assert result == expected
    assert expected.exists()
    assert not (dest / "monorepo").exists()

    clone_call = git_double.calls[0]
    assert "-b" in clone_call and "release/1.0" in clone_call
    assert "--filter=blob:none" in clone_call and "--no-checkout" in clone_call


@pytest.mark.parametrize(
    "variant",
    [
        "/modules/adas/camera",
        r"\\modules\\adas\\camera",
        r"modules\\adas/camera",
        "modules/adas//camera",
        "////modules////adas////camera////",
    ],
)
def test_fetch_normalizes_subdir_variants(tmp_path, git_double, variant):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    expected = dest / Path("modules/adas/camera")
    result = f.fetch(src, dest, subdir=variant)

    assert result == expected
    assert expected.exists()
    assert not (dest / "monorepo").exists()


# ----------------------------
# Errors & edge cases
# ----------------------------

@pytest.mark.parametrize("bad", ["/", "\\", "////", r"\\\\"])
def test_rejects_root_like_subdir(tmp_path, git_double, bad):
    """
    Should reject subdir only when it's provided AND normalizes to empty,
    e.g., '/', '\\', '////', '\\\\\\\\'. An empty string '' is treated as 'no subdir'
    and therefore should NOT raise.
    """
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()
    with pytest.raises(ValueError):
        f.fetch(src, dest, subdir=bad)


def test_destination_collision_on_move(tmp_path, git_double):
    src = "https://gitlab.com/org/monorepo.git"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    subdir = "modules/adas/camera"
    # Pre-create destination path to trigger collision
    (dest / _norm_subdir(subdir)).mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeError) as ei:
        f.fetch(src, dest, subdir=subdir)
    assert "already exists" in str(ei.value)


def test_existing_nonempty_target_repo_raises(tmp_path, git_double):
    # Repo name derived from url: monorepo
    dest = tmp_path / "repos"
    repo_dir = dest / "monorepo"
    dest.mkdir()
    repo_dir.mkdir(parents=True)
    (repo_dir / "dummy.txt").write_text("x")

    f = GitFetcher()
    with pytest.raises(RuntimeError) as ei:
        f.fetch("https://gitlab.com/org/monorepo.git", dest)
    assert "already exists and is not empty" in str(ei.value)


def test_calledprocesserror_is_wrapped_with_sanitized_url(tmp_path, monkeypatch):
    """
    When git fails, the code wraps the error and prefixes a sanitized source URL,
    but the embedded subprocess error may still contain the original argv.
    This test asserts the presence of the sanitized form and does NOT require
    secrets to be absent in the full message.
    """
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

    # Prepare a double that raises on 'clone'
    def _raise_on_clone(argv):
        return "clone" in argv
    double = GitRunDouble(tmp_path)
    double.raise_on = _raise_on_clone
    monkeypatch.setattr("subprocess.run", double)

    # Source with credentials to test sanitizer prefix
    src = "https://user:token@github.com/org/private.git"

    with pytest.raises(RuntimeError) as ei:
        f.fetch(src, dest)

    msg = str(ei.value)
    # Must contain a redacted userinfo marker in the *sanitized prefix*
    assert re.search(r"https?://\*{3}@", msg), msg


# ----------------------------
# Shorthand normalization via env
# ----------------------------

def test_shorthand_normalizes_to_ssh_by_default(tmp_path, git_double):
    """
    Default behavior: PROTO=ssh, USER=git, HOST=gitlab.com
    =>
    clone URL should look like: git@gitlab.com:group/monorepo.git
    """
    src = "group/monorepo"
    dest = tmp_path / "repos"
    dest.mkdir()
    f = GitFetcher()

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
    f = GitFetcher()

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
    f = GitFetcher()

    f.fetch(src, dest)
    clone_call = git_double.calls[0]
    assert any(
        arg.startswith("gitlab@gitlab.com:group/repo.git") for arg in clone_call
    ), f"Unexpected clone args: {clone_call}"