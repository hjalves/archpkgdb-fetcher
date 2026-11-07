import argparse
import logging
import logging.config
import os
import tomllib
from pathlib import Path

from .fetcher import fetcher

CONFIG = os.environ.get("CONFIG", "conf/archpkgdb-fetcher.toml")

log = logging.getLogger(__name__)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config["logging"])
    fetcher(config["fetcher"], config["servers"], force=args.force)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch updated db files for Arch Linux repos"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=CONFIG,
        help="Path to the configuration file (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force fetching of repository files even if they are up-to-date",
    )
    args = parser.parse_args()
    return args


def load_config(config_path: str | Path) -> dict:
    log.debug("Loading configuration from %s", config_path)
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    # TODO: Validate and process the configuration as needed
    return config


def setup_logging(logging_config: dict) -> None:
    logging.config.dictConfig(logging_config)
    logging.captureWarnings(True)
    log.debug("Logging has been configured")
