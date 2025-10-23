import argparse
import sys
import logging
from artifetch.core import fetch, FetchError

# Configure a basic logger for CLI
logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        prog="artifetch",
        description="Universal artifact fetcher for Artifactory, GitLab, and Git."
    )

    parser.add_argument("source", help="Source URL or identifier (e.g. gitlab://project/job or https://repo.git)")
    parser.add_argument("--dest", "-d", help="Destination folder (default: current directory)", default=".")
    parser.add_argument("--provider", "-p", choices=["gitlab", "artifactory", "git"], help="Specify provider explicitly")
    parser.add_argument("--branch", "-b", help="(git) Branch/tag/ref to checkout")
    parser.add_argument("--subdir", "-s", help="(git) Only materialize this subdirectory using sparse-checkout")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        result = fetch(
            source=args.source,
            dest=args.dest,
            provider=args.provider,
            branch=args.branch,
            subdir=args.subdir,
        )
        logger.info(f"Successfully fetched: {result}")
    except FetchError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()