from __future__ import annotations
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Callable, Tuple, Optional

__all__ = [
    "ensure_dir",
    "rmtree_win_safe",
]

def ensure_dir(path: Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _make_trash_name(path: Path) -> Path:
    """Create a unique sibling for rename-away deletion."""
    return path.with_name(f"{path.name}._del_{os.getpid()}_{int(time.time()*1000)}")

def _on_rm_error(func: Callable, path: str, exc_info: Tuple[type, BaseException, object]):
    """Clear read-only bit and retry the failed remove/rmdir."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass
    # Retry the original operation (func is os.remove / os.rmdir)
    try:
        func(path)
    except PermissionError:
        # Let outer retry handle another attempt
        raise

def rmtree_win_safe(path: Path, *, retries: int = 6, delay: float = 0.2) -> None:
    """
    Robust directory removal (especially on Windows):
    1) Try to rename the directory away first.
    2) Then shutil.rmtree with an onerror handler.
    3) Retry with exponential backoff on PermissionError.
    """
    path = Path(path)
    target = path
    try:
        trash = _make_trash_name(path)
        os.replace(path, trash)  # atomic rename if possible
        target = trash
    except Exception:
        target = path

    last_err: Optional[BaseException] = None
    for i in range(retries):
        try:
            shutil.rmtree(target, onerror=_on_rm_error)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(delay * (2 ** i))
    # Final attempt (let it raise for visibility)
    shutil.rmtree(target, onerror=_on_rm_error)