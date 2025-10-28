import io
import os
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest

from artifetch.fetchers.repo_content import RepositoryContentFetcher

# ---------------------------
# Helpers
# ---------------------------

class MockResponse:
    def __init__(self, *, content_bytes=b"", status_code=200, headers=None, json_data=None):
        self._bytes = content_bytes
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self._iterated = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise Exception(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=8192):
        # yield once to simulate streaming
        stream = io.BytesIO(self._bytes)
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            yield chunk

# Build an in-memory GitLab archive.zip

def make_zip_bytes(entries):
    # entries: list of (name_in_repo, bytes)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Simulate GitLab's top-level folder e.g. owner-repo-<sha>/
        top = 'ns-repo-abc123/'
        # ensure directories are present to avoid surprises
        zf.writestr(top, '')
        for rel, data in entries:
            # Ensure forward slashes
            rel = rel.replace('\\', '/')
            zf.writestr(top + rel, data)
    return mem.getvalue()

# Capture requests.get calls so we can assert URL/params usage per test

class RequestCapture:
    def __init__(self):
        self.calls = []  # list of dicts with url, params
        self.next_zip = None
        self.next_file_bytes = None

    def set_zip(self, entries):
        self.next_zip = make_zip_bytes(entries)

    def set_file(self, data: bytes):
        self.next_file_bytes = data

    def __call__(self, url, *, headers=None, params=None, stream=False, allow_redirects=True, timeout=None):
        self.calls.append({
            'url': url,
            'params': dict(params or {}),
            'headers': dict(headers or {}),
            'stream': stream,
        })
        if url.endswith('/repository/archive.zip'):
            assert self.next_zip is not None, 'Archive requested but no zip configured'
            return MockResponse(content_bytes=self.next_zip, status_code=200)
        elif '/repository/files/' in url and url.endswith('/raw'):
            assert self.next_file_bytes is not None, 'File requested but no file bytes configured'
            return MockResponse(content_bytes=self.next_file_bytes, status_code=200)
        else:
            return MockResponse(status_code=404)

# ---------------------------
# Tests
# ---------------------------

@pytest.fixture
def fetcher(monkeypatch):
    # Ensure predictable API base fallback unless tests override
    monkeypatch.delenv('ARTIFETCH_GITLAB_API_BASE', raising=False)
    monkeypatch.setenv('ARTIFETCH_GIT_HOST', 'gitlab.com')
    return RepositoryContentFetcher()


def test_fetch_repo_default_branch_downloads_archive(tmp_path, fetcher, monkeypatch):
    rc = RequestCapture()
    rc.set_zip([
        ('README.md', b'# readme'),
        ('src/app.py', b'print(1)')
    ])

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        out = fetcher.fetch('gitlab://group/sub/repo', tmp_path, kind='repo')

    # output directory populated
    assert out == tmp_path
    assert (tmp_path / 'README.md').read_bytes() == b'# readme'
    assert (tmp_path / 'src' / 'app.py').read_text() == 'print(1)'

    # Verify the URL and params
    [call] = rc.calls
    assert call['url'].endswith('/api/v4/projects/group%2Fsub%2Frepo/repository/archive.zip')
    assert call['params'].get('sha') == 'HEAD'  # default ref
    assert 'path' not in call['params']  # whole repo


def test_fetch_dir_flattens_and_uses_ref(tmp_path, fetcher):
    rc = RequestCapture()
    # Zip contains a requested folder plus other content which should be ignored
    rc.set_zip([
        ('services/auth/a.txt', b'a'),
        ('services/auth/nested/b.txt', b'b'),
        ('docs/readme.md', b'ignore')
    ])

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        out = fetcher.fetch('gitlab://group/repo@mybranch//services/auth', tmp_path, kind='dir')

    # Flattened: 'services/auth/' stripped
    assert (tmp_path / 'a.txt').read_bytes() == b'a'
    assert (tmp_path / 'nested' / 'b.txt').read_bytes() == b'b'
    assert not (tmp_path / 'docs').exists()

    [call] = rc.calls
    assert call['params'].get('sha') == 'mybranch'
    assert call['params'].get('path') == 'services/auth'


def test_fetch_file_overwrites_existing(tmp_path, fetcher):
    # Pre-create destination file to verify overwrite
    target = tmp_path / 'CHANGELOG.md'
    target.write_text('old')

    rc = RequestCapture()
    rc.set_file(b'new content')

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        path = fetcher.fetch('gitlab://group/repo@v1.2.3//CHANGELOG.md', tmp_path)

    assert path == target
    assert target.read_bytes() == b'new content'

    [call] = rc.calls
    # repository/files/<file>/raw?ref=v1.2.3
    assert '/repository/files/' in call['url'] and call['url'].endswith('/raw')
    assert call['params'].get('ref') == 'v1.2.3'


def test_existing_dir_files_overwritten_on_dir_extract(tmp_path, fetcher):
    # Pre-create a file that will be replaced by extraction
    (tmp_path / 'nested').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'nested' / 'b.txt').write_text('oldb')

    rc = RequestCapture()
    rc.set_zip([
        ('services/auth/nested/b.txt', b'NEWB')
    ])

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://group/repo@main//services/auth', tmp_path, kind='dir')

    assert (tmp_path / 'nested' / 'b.txt').read_text() == 'NEWB'


def test_supports_web_urls_tree_blob_and_root(tmp_path, monkeypatch):
    # Ensure we don't use env base for this test; API base should come from the host in URL
    monkeypatch.delenv('ARTIFETCH_GITLAB_API_BASE', raising=False)
    monkeypatch.delenv('ARTIFETCH_GIT_HOST', raising=False)

    fetcher = RepositoryContentFetcher()
    rc = RequestCapture()

    # 1) tree
    rc.set_zip([('path/x.txt', b'x')])
    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://https://gitlab.example.com/group/repo/-/tree/main/path', tmp_path)
    call1 = rc.calls[-1]
    assert call1['url'].startswith('https://gitlab.example.com/api/v4/projects/group%2Frepo/repository/archive.zip')
    assert call1['params'].get('sha') == 'main'
    assert call1['params'].get('path') == 'path'

    # 2) blob
    rc.set_file(b'filebytes')
    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        p = fetcher.fetch('gitlab://https://gitlab.example.com/group/repo/-/blob/dev/file.txt', tmp_path)
    assert p.name == 'file.txt'
    call2 = rc.calls[-1]
    assert call2['url'].startswith('https://gitlab.example.com/api/v4/projects/group%2Frepo/repository/files/')
    assert call2['params'].get('ref') == 'dev'

    # 3) root (HEAD)
    rc.set_zip([('README.md', b'1')])
    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://https://gitlab.example.com/group/repo', tmp_path)
    call3 = rc.calls[-1]
    assert call3['params'].get('sha') == 'HEAD'


def test_api_base_env_precedence_for_self_hosted(tmp_path, monkeypatch):
    monkeypatch.setenv('ARTIFETCH_GITLAB_API_BASE', 'https://self.host/custom/api/v4')
    monkeypatch.setenv('ARTIFETCH_GIT_HOST', 'ignored.example.com')
    fetcher = RepositoryContentFetcher()

    rc = RequestCapture()
    rc.set_file(b'x')

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://team/repo@r1//file.txt', tmp_path)

    [call] = rc.calls
    assert call['url'].startswith('https://self.host/custom/api/v4/projects/team%2Frepo/repository/files/')


def test_invalid_scheme_and_bad_urls(tmp_path, fetcher):
    # Unsupported scheme
    with pytest.raises(ValueError):
        fetcher.fetch('github://owner/repo', tmp_path)

    # Missing repo segment in web URL
    with pytest.raises(ValueError):
        fetcher.fetch('gitlab://https://gitlab.example.com/justone', tmp_path)

    # Missing repo in compact grammar
    with pytest.raises(ValueError):
        fetcher.fetch('gitlab://onlyns', tmp_path)


def test_kind_override_dir_when_path_has_dots(tmp_path, fetcher):
    rc = RequestCapture()
    rc.set_zip([('folder.with.dots/a.txt', b'a')])

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://group/repo@main//folder.with.dots', tmp_path, kind='dir')

    [call] = rc.calls
    # Ensured archive endpoint (not the file/raw endpoint)
    assert call['url'].endswith('/repository/archive.zip')
    assert call['params'].get('path') == 'folder.with.dots'


def test_sends_gitlab_token_header_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv('GITLAB_TOKEN', 'abc123')
    fetcher = RepositoryContentFetcher()
    
    from artifetch.fetchers.repo_content import RepositoryContentFetcher as _RCF  # ensure module re-reads env in _gl_headers
    rc = RequestCapture()
    rc.set_file(b'xyz')

    with patch('artifetch.fetchers.repo_content.requests.get', side_effect=rc):
        fetcher.fetch('gitlab://group/repo@main//file.txt', tmp_path)

    [call] = rc.calls
    assert call['headers'].get('PRIVATE-TOKEN') == 'abc123'