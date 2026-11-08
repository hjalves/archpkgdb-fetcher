import datetime
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from string import Template
from typing import Any


def datetime_is_aware(value: datetime.datetime) -> bool:
    """
    Determine if a given datetime.datetime is aware.

    The concept is defined in Python's docs:
    https://docs.python.org/library/datetime.html#datetime.tzinfo

    Assuming value.tzinfo is either None or a proper datetime.tzinfo,
    value.utcoffset() implements the appropriate logic.

    Args:
        value (datetime.datetime): The datetime object to check.

    Returns:
        bool: True if the datetime is aware, False otherwise.
    """
    return value.utcoffset() is not None


def now() -> datetime.datetime:
    """
    Return the current datetime with UTC timezone.

    Returns:
        datetime.datetime: The current datetime with UTC timezone.
    """
    return datetime.datetime.now(datetime.UTC)


def json_serial(obj: object) -> str:
    """
    JSON serializer for objects not serializable by default.

    Currently, it only supports datetime.datetime objects, which are
    converted to ISO 8601 formatted strings.
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")


def load_cache(cache_file: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load the cache from a JSON file.

    If the file does not exist, an empty dictionary is returned.

    Args:
        cache_file (str | Path): Path to the cache file.

    Returns:
        dict[str, dict[str, Any]]: The loaded cache data.
    """
    cache_file = Path(cache_file)
    if not cache_file.exists():
        return {}
    with open(cache_file, "r", encoding="utf-8") as f:
        data: Any = json.load(f)
    if (
        not isinstance(data, dict)
        or not all(isinstance(v, dict) for v in data.values())
        or not all(isinstance(k, str) for k in data)
    ):
        raise ValueError(
            "Cache must be a JSON object containing objects with string keys"
        )
    return data


def save_cache(cache_file: str | Path, data: dict[str, dict[str, Any]]) -> None:
    """
    Save the cache to a JSON file.

    Args:
        cache_file (str | Path): Path to the cache file.
        data (dict[str, dict[str, Any]]): The cache data to save.
    """
    cache_file = Path(cache_file)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=json_serial)


def merge_cache(
    old_cache: dict[str, dict[str, Any]], new_cache: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """
    Merge two cache dictionaries.

    Args:
        old_cache (dict[str, dict[str, Any]]): The original cache.
        new_cache (dict[str, dict[str, Any]]): The new cache to merge into the original.

    Returns:
        dict[str, dict[str, Any]]: The merged cache.
    """
    merged = old_cache.copy()
    for server, server_cache in new_cache.items():
        for repo, repo_cache in server_cache.items():
            if server not in merged:
                merged[server] = {}
            merged[server][repo] = repo_cache
    return merged


def interpolate_path(
    template: str, arch: str, repo: str, date: datetime.date | None
) -> str:
    # Interpolate the template with the provided arch, repo, and date values
    interpolated = Template(template).substitute(
        arch=arch,
        repo=repo,
        year=f"{date.year:04d}" if date else "",
        month=f"{date.month:02d}" if date else "",
        day=f"{date.day:02d}" if date else "",
    )
    # Interpolate date and time placeholders using the current time (example: %Y%m%d)
    return now().strftime(interpolated)


def sha256sum(file_path: str | Path) -> str:
    """
    Compute the SHA256 checksum of a file.

    Args:
        file_path (str | Path): Path to the file.

    Returns:
        str: The SHA256 checksum of the file.
    """
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def iter_files(root: str | Path, pattern: str) -> Iterator[Path]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"{root} does not exist")
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    for path in sorted(root.rglob(pattern)):
        if path.is_file():
            yield path
