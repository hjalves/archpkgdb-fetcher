import logging
import os
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from string import Template
from typing import Any

import requests

from .utils import datetime_is_aware, load_cache, merge_cache, now, save_cache

log = logging.getLogger(__name__)


def fetcher(fetcher_config: dict[str, Any], servers_config: list[dict]) -> None:
    """
    Fetch all repositories based on the provided configuration.

    Args:
        fetcher_config (dict[str, Any]): Configuration for the fetcher.
        servers_config (list[dict[str, Any]]): List of server configurations.
    """
    archs = fetcher_config["archs"]
    repos = fetcher_config["repos"]
    root = fetcher_config["root"]
    dirfmt = fetcher_config["dirfmt"]
    cache_file = fetcher_config["cache"]
    user_agent = fetcher_config["user_agent"]

    # Select servers with the role "current"
    servers = [s["url"] for s in servers_config if s["role"] == "current"]

    log.info("Starting fetcher with archs: %s and repos: %s", archs, repos)
    caches = load_cache(cache_file)
    new_caches = fetch_repos(archs, repos, servers, root, dirfmt, caches, user_agent)
    save_cache(cache_file, merge_cache(caches, new_caches))
    report(new_caches)


def report(caches: dict[str, dict]) -> None:
    for server, server_cache in caches.items():
        log.info("Server: %s", server)
        for repo_key, repo_cache in server_cache.items():
            log.info("- Repo: %s, Status: %s", repo_key, repo_cache.get("status"))


def fetch_repos(
    archs: list[str],
    repos: list[str],
    servers: list[str],
    root: str | Path,
    dirfmt: str,
    caches: dict[str, dict],
    user_agent: str,
) -> dict[str, dict]:
    root = Path(root)
    old_server_caches = caches
    server_caches = {}

    for arch in archs:
        dir_name = Template(dirfmt).substitute(arch=arch)
        dir_name = now().strftime(dir_name)

        session = requests.Session()
        session.headers.update(
            {"Accept": "application/octet-stream", "User-Agent": user_agent}
        )

        target_dir = root / dir_name
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            # TODO: Implement server selection logic based on availability, priority, etc.
            server = servers[0]
            old_server_cache = old_server_caches.get(server, {})
            server_cache = {}

            for repo in repos:
                cache_key = f"{repo}/{arch}"
                cache = old_server_cache.get(cache_key, {})
                result = handle_server_repository(
                    session, cache, arch, repo, server, target_dir
                )
                server_cache[cache_key] = result

            server_caches[server] = server_cache

        finally:
            # check if there's .tmp files and remove them
            for tmp_file in target_dir.glob("*.tmp"):
                tmp_file.unlink()
            # check if directory is empty and remove it if it is
            if not any(target_dir.iterdir()):
                target_dir.rmdir()

    return server_caches


def handle_server_repository(
    session: requests.Session,
    cache: dict[str, str | datetime | None],
    arch: str,
    repo: str,
    server: str,
    target_dir: Path,
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
    assert last_modified is None or datetime_is_aware(last_modified)

    download_url = Template(server).substitute(arch=arch, repo=repo)
    download_url = download_url.rstrip("/") + f"/{repo}.db"
    target_path = target_dir / f"{repo}.db"

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
        "etag": cache.get("etag"),
        "last_modified": cache.get("last_modified"),
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
            # Read the response body to release the connection
            _ = response.content
            result["status"] = f"failed ({response.status_code})"
            return result

        if response.status_code == 304:
            log.debug("%s not modified since last fetch", download_url)
            # Read the response body to release the connection
            _ = response.content
            result["status"] = "not_modified"
            return result

        # Check if the response contains the expected content type
        content_type = response.headers.get("Content-Type", "")
        if "application/octet-stream" not in content_type:
            log.error("Unexpected content type for %s: %s", download_url, content_type)
            _ = response.content
            result["status"] = f"failed (unexpected content type: {content_type})"
            return result

        log.debug("Fetching repository file from URL: %s", download_url)
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
            assert datetime_is_aware(last_modified), (
                "Last-Modified header is not timezone aware"
            )
            result["last_modified"] = last_modified
            os.utime(
                target_path, (last_modified.timestamp(), last_modified.timestamp())
            )

        return result
