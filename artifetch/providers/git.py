"""Clone or fetch from Git repositories."""

class GitProvider:
    def __init__(self):
        """Prepare git client or detect git binary."""
        pass

    def fetch(self, repo_ref: str, dest: str = ".", **kwargs):
        """Clone repository or checkout branch."""
        pass