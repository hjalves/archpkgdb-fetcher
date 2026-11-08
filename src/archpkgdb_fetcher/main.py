import argparse
import logging
from datetime import date
from typing import Any

from .config import default_config_path, load_config, setup_logging, version
from .fetcher import fetcher

log = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    logging_config = config["logging"]
    setup_logging(logging_config, key=args.log_config)
    log.info(
        "Starting archpkgdb-fetcher %s with arguments: %s", version(), str(args)[10:-1]
    )
    try:
        updated = fetcher(
            config["fetcher"],
            config["servers"],
            force=args.force,
            archive_date=args.archive_date,
        )
        report(updated)
    except Exception as e:
        log.critical("An error occurred: %s", e, exc_info=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch updated db files for Arch Linux repos",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {version()}",
        help="Show the version of archpkgdb-fetcher",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=default_config_path(),
        help="Path to the configuration file (default: %(default)s)",
    )
    parser.add_argument(
        "-l",
        "--log-config",
        type=str,
        default="default",
        help="Logging configuration to use (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force fetching of repository files even if they are up-to-date",
    )
    parser.add_argument(
        "-a",
        "--archive-date",
        type=str,
        help="The date of the archive to fetch (format: YYYY-MM-DD) or 'today'",
    )
    args = parser.parse_args()
    if args.archive_date == "today":
        args.archive_date = date.today()
    elif args.archive_date:
        args.archive_date = date.fromisoformat(args.archive_date)
    return args


def report(caches: dict[str, dict[str, Any]]) -> None:
    for server, server_cache in caches.items():
        log.info("Server: %s", server)
        for repo_key, repo_cache in server_cache.items():
            log.info(
                "> %s, %s, last modified: %s",
                repo_key,
                repo_cache.get("status"),
                repo_cache.get("last_modified"),
            )
