import logging
import logging.config
import tomllib
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent.parent.parent

CONFIG_SEARCH_PATHS = [
    Path.cwd() / "config.toml",
    Path.home() / ".config" / "archpkgdb-fetcher" / "archpkgdb-fetcher.toml",
    BASE_DIR / "conf" / "archpkgdb-fetcher.toml",
]

log = logging.getLogger(__name__)


def version() -> str:
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("archpkgdb-fetcher")
    except ImportError:
        return "unknown"


def default_config_path() -> Path:
    for path in CONFIG_SEARCH_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("No configuration file found in search paths")


def load_config(config_path: str | Path) -> dict[str, Any]:
    log.debug("Loading configuration from %s", config_path)
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    # TODO: Validate and process the configuration as needed
    return config


def setup_logging(logging_config: dict[str, Any], key: str) -> None:
    if key not in logging_config:
        raise ValueError(f"Logging configuration '{key}' not found in the config file")
    logging.config.dictConfig(logging_config[key])
    logging.captureWarnings(True)
    log.debug("Logging has been configured")
