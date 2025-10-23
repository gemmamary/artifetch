import argparse
import sys
from artifetch.core import fetch, FetchError


def main():
    parser = argparse.ArgumentParser(
        prog="artifetch",
        description="Universal artifact fetcher for Artifactory, GitLab, and Git."
    )

    parser.add_argument(
        "source",
        help="Source URL or identifier (e.g. gitlab://project/job or https://repo.git)"
    )
    parser.add_argument(
        "--dest",
        "-d",
        help="Destination folder (default: current directory)",
        default="."
    )
    parser.add_argument(
        "--provider",
        "-p",
        choices=["gitlab", "artifactory", "git"],
        help="Specify provider explicitly (auto-detected otherwise)"
    )

    args = parser.parse_args()

    try:
        fetch(source=args.source, dest=args.dest, provider=args.provider)
    except FetchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
