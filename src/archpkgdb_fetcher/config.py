import logging
import logging.config
import os
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from importlib.resources import files
from pathlib import Path
from typing import Any

from .utils import merge_dicts

CONFIG_SEARCH_PATHS = [
    Path.cwd() / "config.toml",
    Path.home() / ".config" / "archpkgdb-fetcher.toml",
]

log = logging.getLogger(__name__)


def version() -> str:
    try:
        return pkg_version("archpkgdb-fetcher")
    except PackageNotFoundError:
        return "unknown"


def find_config_file() -> Path | None:
    env = os.getenv("ARCHPKGDB_CONFIG")
    if env:
        return Path(env).resolve()
    for path in CONFIG_SEARCH_PATHS:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def load_config(config_path: str | Path | None) -> dict[str, Any]:
    if config_path is None:
        resource = files("archpkgdb_fetcher.data").joinpath("defaults.toml")
        config = tomllib.loads(resource.read_text(encoding="utf-8"))
        return config

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

    # Deal with extends
    if "extends" in logging_config[key]:
        base_key = logging_config[key].pop("extends")
        if base_key not in logging_config:
            raise ValueError(
                f"Base logging configuration '{base_key}' not found in the config file"
            )
        logging_config[key] = merge_dicts(logging_config[base_key], logging_config[key])

    logging.config.dictConfig(logging_config[key])
    logging.captureWarnings(True)
    # Log the root logger's handlers for debugging purposes
    handlers = ", ".join(str(h) for h in logging.getLogger().handlers)
    log.debug("Logging has been configured with key '%s', handlers: %s", key, handlers)
