import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from archpkgdb_fetcher.utils import (
    datetime_is_aware,
    load_cache,
    merge_cache,
    now,
    save_cache,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2025, 1, 1), False),
        (datetime(2025, 1, 1, tzinfo=UTC), True),
        (
            datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=2))),
            True,
        ),
    ],
)
def test_datetime_is_aware(value: datetime, expected: bool) -> None:
    assert datetime_is_aware(value) is expected


def test_now_returns_aware_utc_datetime() -> None:
    value = now()

    assert value.tzinfo is UTC
    assert datetime_is_aware(value)


def test_load_cache_returns_empty_mapping_for_missing_file(tmp_path: Path) -> None:
    assert load_cache(tmp_path / "cache.json") == {}


def test_save_and_load_cache_round_trip_datetimes(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.json"
    fetched_at = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)
    cache = {"https://example.test": {"fetch_time": fetched_at}}

    save_cache(cache_file, cache)

    assert json.loads(cache_file.read_text(encoding="utf-8")) == {
        "https://example.test": {
            "fetch_time": fetched_at.isoformat().replace("+00:00", "Z")
        }
    }
    assert load_cache(cache_file) == {
        "https://example.test": {
            "fetch_time": fetched_at.isoformat().replace("+00:00", "Z")
        }
    }


def test_merge_cache_updates_repositories_and_preserves_others() -> None:
    old_cache = {
        "server": {"core/x86_64": {"status": "old"}, "extra/x86_64": {"status": "kept"}}
    }
    new_cache = {"server": {"core/x86_64": {"status": "fetched"}}}

    merged = merge_cache(old_cache, new_cache)

    assert merged == {
        "server": {
            "core/x86_64": {"status": "fetched"},
            "extra/x86_64": {"status": "kept"},
        }
    }
