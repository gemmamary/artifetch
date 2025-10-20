from pathlib import Path

def setup_logging():
    """Configure global logging."""
    pass

def ensure_dir(path: str):
    """Create directory if it doesn’t exist."""
    Path(path).mkdir(parents=True, exist_ok=True)