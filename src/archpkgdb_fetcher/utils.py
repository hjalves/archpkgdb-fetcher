import datetime
import json
from pathlib import Path


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


def json_serial(obj: dict) -> str:
    """
    JSON serializer for objects not serializable by default.

    Currently, it only supports datetime.datetime objects, which are
    converted to ISO 8601 formatted strings.

    Args:
        obj (dict): The object to serialize.

    Returns:
        str: The JSON-serializable string representation of the object.
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")


def load_cache(cache_file: str | Path) -> dict[str, dict]:
    """
    Load the cache from a JSON file.

    If the file does not exist, an empty dictionary is returned.

    Args:
        cache_file (str | Path): Path to the cache file.

    Returns:
        dict[str, dict]: The loaded cache data.
    """
    cache_file = Path(cache_file)
    if not cache_file.exists():
        return {}
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_file: str | Path, data: dict[str, dict]) -> None:
    """
    Save the cache to a JSON file.

    Args:
        cache_file (str | Path): Path to the cache file.
        data (dict[str, dict]): The cache data to save.
    """
    # Converts datetime objects to ISO format strings for JSON serialization
    cache_file = Path(cache_file)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=json_serial)


def merge_cache(
    old_cache: dict[str, dict], new_cache: dict[str, dict]
) -> dict[str, dict]:
    """
    Merge two cache dictionaries.

    Args:
        old_cache (dict[str, dict]): The original cache.
        new_cache (dict[str, dict]): The new cache to merge into the original.

    Returns:
        dict[str, dict]: The merged cache.
    """
    merged = old_cache.copy()
    for server, server_cache in new_cache.items():
        for repo, repo_cache in server_cache.items():
            if server not in merged:
                merged[server] = {}
            merged[server][repo] = repo_cache
    return merged
