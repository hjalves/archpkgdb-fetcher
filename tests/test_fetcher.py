import importlib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from archpkgdb_fetcher.fetcher import fetch_repository_file, fetcher

fetcher_module = importlib.import_module("archpkgdb_fetcher.fetcher")


def make_response(
    *,
    status_code: int = 200,
    ok: bool = True,
    headers: dict[str, str] | None = None,
    chunks: list[bytes] | None = None,
) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status_code
    response.ok = ok
    response.headers = headers or {}
    response.content = b""
    response.iter_content.return_value = chunks or []
    return response


def test_fetch_repository_file_writes_content_and_returns_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_path = tmp_path / "core.db"
    modified = "Wed, 21 Oct 2015 07:28:00 GMT"
    response = make_response(
        headers={
            "Content-Type": "application/octet-stream",
            "ETag": '"abc123"',
            "Last-Modified": modified,
        },
        chunks=[b"database", b"", b" contents"],
    )
    session = MagicMock()
    session.get.return_value = response
    fetched_at = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)
    monkeypatch.setattr(fetcher_module, "now", lambda: fetched_at)

    result = fetch_repository_file(
        session, "https://example.test/core.db", target_path, None, None
    )

    assert result == {
        "status": "fetched",
        "fetch_time": fetched_at,
        "fetch_path": str(target_path),
        "etag": '"abc123"',
        "last_modified": datetime(2015, 10, 21, 7, 28, tzinfo=UTC),
    }
    assert target_path.read_bytes() == b"database contents"
    assert not target_path.with_suffix(".db.tmp").exists()
    session.get.assert_called_once_with(
        "https://example.test/core.db", headers={}, stream=True
    )


def test_fetch_repository_file_sends_validators_and_handles_not_modified(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "core.db"
    target_path.write_bytes(b"existing database")
    response = make_response(status_code=304)
    session = MagicMock()
    session.get.return_value = response
    last_modified = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)

    result = fetch_repository_file(
        session,
        "https://example.test/core.db",
        target_path,
        '"abc123"',
        last_modified,
    )

    assert result == {"status": "not_modified"}
    assert target_path.read_bytes() == b"existing database"
    session.get.assert_called_once_with(
        "https://example.test/core.db",
        headers={
            "If-None-Match": '"abc123"',
            "If-Modified-Since": "Thu, 02 Jan 2025 03:04:00 GMT",
        },
        stream=True,
    )


@pytest.mark.parametrize(
    ("status_code", "ok", "headers", "expected_status"),
    [
        (404, False, {}, "failed (404)"),
        (
            200,
            True,
            {"Content-Type": "text/plain"},
            "failed (unexpected content type: text/plain)",
        ),
    ],
)
def test_fetch_repository_file_rejects_unsuccessful_or_unexpected_responses(
    tmp_path: Path,
    status_code: int,
    ok: bool,
    headers: dict[str, str],
    expected_status: str,
) -> None:
    target_path = tmp_path / "core.db"
    response = make_response(status_code=status_code, ok=ok, headers=headers)
    session = MagicMock()
    session.get.return_value = response

    result = fetch_repository_file(
        session, "https://example.test/core.db", target_path, None, None
    )

    assert result == {"status": expected_status}
    assert not target_path.exists()


@pytest.mark.parametrize(
    ("servers", "archs", "repos", "error"),
    [
        ([], ["x86_64"], ["core"], "No servers"),
        (
            [{"url": "https://example.test", "role": "current"}],
            [],
            ["core"],
            "No architectures",
        ),
        (
            [{"url": "https://example.test", "role": "current"}],
            ["x86_64"],
            [],
            "No repositories",
        ),
    ],
)
def test_fetcher_rejects_missing_required_configuration(
    tmp_path: Path,
    servers: list[dict[str, str]],
    archs: list[str],
    repos: list[str],
    error: str,
) -> None:
    config = {
        "archs": archs,
        "repos": repos,
        "current": str(tmp_path / "$repo" / "$arch.db"),
        "cache": str(tmp_path / "cache.json"),
        "user_agent": "test",
    }

    with pytest.raises(ValueError, match=error):
        fetcher(config, servers)
