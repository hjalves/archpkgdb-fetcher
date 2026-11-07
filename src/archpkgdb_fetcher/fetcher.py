import logging
import os
from datetime import UTC, date, datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

from .utils import (
    datetime_is_aware,
    interpolate_path,
    load_cache,
    merge_cache,
    now,
    save_cache,
)

log = logging.getLogger(__name__)


def fetcher(
    fetcher_config: dict[str, Any],
    servers_config: list[dict[str, Any]],
    force: bool = False,
    archive_date: date | None = None,
) -> dict[str, dict]:
    """
    Fetch all repositories based on the provided configuration.

    Args:
        fetcher_config (dict[str, Any]): Configuration for the fetcher.
        servers_config (list[dict[str, Any]]): List of server configurations.
        force (bool): Force fetching of repository files even if they are up-to-date.
        archive_date (date | None): The date of the archive to fetch. If None, fetch the current repositories.
    """
    archs = fetcher_config["archs"]
    repos = fetcher_config["repos"]
    cache_file = fetcher_config["cache"]
    user_agent = fetcher_config["user_agent"]

    role = "archive" if archive_date else "current"
    path = fetcher_config[role]
    servers = [s["url"] for s in servers_config if s["role"] == role]

    log.info("Starting fetcher with archs: %s, repos: %s, role: %s", archs, repos, role)
    if archive_date:
        log.info("Fetching archive for date: %s", archive_date)
    if force:
        log.info("Force fetching is enabled")

    if archive_date and archive_date > date.today():
        raise ValueError(f"Archive date cannot be in the future: {archive_date}")
    if not servers:
        raise ValueError(f"No servers with role '{role}' found")
    if not archs:
        raise ValueError("No architectures specified")
    if not repos:
        raise ValueError("No repositories specified")

    if force or archive_date:
        caches = {}
    else:
        caches = load_cache(cache_file)

    updated_caches = fetch_repos(
        archs, repos, servers, path, caches, user_agent, archive_date
    )
    if not archive_date:
        # Only update the cache for the current repositories, not for archive fetches
        if force:
            # If force is enabled, reload the existing cache to merge with updated caches
            caches = load_cache(cache_file)
        save_cache(cache_file, merge_cache(caches, updated_caches))

    return updated_caches


def fetch_repos(
    archs: list[str],
    repos: list[str],
    servers: list[str],
    path: str,
    caches: dict[str, dict],
    user_agent: str,
    archive_date: date | None = None,
) -> dict[str, dict]:
    server_caches = {}

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})

    for arch in archs:
        # TODO: Implement server selection logic based on availability, priority, etc.
        server = servers[0]
        old_server_cache = caches.get(server, {})
        server_cache = {}

        for repo in repos:
            target_path = Path(interpolate_path(path, arch, repo, archive_date))
            parent_dir = target_path.parent

            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
                cache_key = f"{repo}/{arch}"
                cache = old_server_cache.get(cache_key, {})
                server_cache[cache_key] = handle_server_repository(
                    session,
                    cache,
                    arch,
                    repo,
                    server,
                    target_path,
                    archive_date,
                )

            finally:
                # check if there's .tmp files and remove them
                for tmp_file in parent_dir.glob("*.tmp"):
                    tmp_file.unlink()
                # check if directory is empty and remove it if it is
                # TODO: we might want to recursively remove empty parent dirs as well
                if not any(parent_dir.iterdir()):
                    parent_dir.rmdir()

            server_caches[server] = server_cache

    return server_caches


def handle_server_repository(
    session: requests.Session,
    cache: dict[str, str | datetime | None],
    arch: str,
    repo: str,
    server: str,
    target_path: Path,
    archive_date: date | None,
) -> dict[str, str | datetime | None]:
    etag_value = cache.get("etag")
    etag = etag_value if isinstance(etag_value, str) else None
    last_modified_iso = cache.get("last_modified")
    last_modified = (
        last_modified_iso
        if isinstance(last_modified_iso, datetime)
        else datetime.fromisoformat(last_modified_iso)
        if last_modified_iso
        else None
    )
    if last_modified is not None and not datetime_is_aware(last_modified):
        raise ValueError("Cached last_modified datetime is not timezone aware")

    # If last_modified is not provided, use the file's modification time as a fallback
    if not last_modified and target_path.exists():
        log.debug("No last_modified provided, using file's mtime for %s", target_path)
        last_modified = datetime.fromtimestamp(target_path.stat().st_mtime, tz=UTC)

    download_url = interpolate_path(server, arch, repo, archive_date)
    download_url = download_url.rstrip("/") + f"/{repo}.db"

    check_time = now()
    try:
        updated = fetch_repository_file(
            session, download_url, target_path, etag, last_modified
        )
    except Exception:
        log.exception("Error fetching repository file %s", download_url)
        updated = {"status": "error"}

    return {
        "repo": repo,
        "arch": arch,
        "check_time": check_time,
        "fetch_time": cache.get("fetch_time"),
        "etag": etag,
        "last_modified": last_modified,
        **updated,
    }


def fetch_repository_file(
    session: requests.Session,
    download_url: str,
    target_path: Path,
    etag: str | None,
    last_modified: datetime | None,
) -> dict[str, str | datetime]:

    tmp_path = target_path.with_suffix(".db.tmp")

    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = format_datetime(
            last_modified.astimezone(UTC), usegmt=True
        )

    with session.get(download_url, headers=headers, stream=True) as response:
        result: dict[str, str | datetime] = {}

        if not response.ok:
            log.error("Failed to fetch %s: HTTP %s", download_url, response.status_code)
            # Read the response body to keep the connection reusable
            _ = response.content
            result["status"] = f"failed ({response.status_code})"
            return result

        if response.status_code == 304:
            log.debug("%s not modified since last fetch", download_url)
            _ = response.content
            result["status"] = "not_modified"
            return result

        content_type = response.headers.get("Content-Type", "")
        if "application/octet-stream" not in content_type:
            log.error("Unexpected content type for %s: %s", download_url, content_type)
            _ = response.content
            result["status"] = f"failed (unexpected content type: {content_type})"
            return result

        log.debug("Fetching file from URL %s to %s", download_url, target_path)
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        os.replace(tmp_path, target_path)

        result["status"] = "fetched"
        result["fetch_time"] = now()

        etag_header = response.headers.get("ETag")
        if etag_header:
            result["etag"] = etag_header

        last_modified_header = response.headers.get("Last-Modified")
        if last_modified_header:
            last_modified = parsedate_to_datetime(last_modified_header)
            if not datetime_is_aware(last_modified):
                raise ValueError("Last-Modified header is not timezone aware")
            result["last_modified"] = last_modified
            os.utime(
                target_path, (last_modified.timestamp(), last_modified.timestamp())
            )

        return result
