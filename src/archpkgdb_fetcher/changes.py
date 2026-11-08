import argparse
import json
import logging
import os
import tarfile
from compression import zstd
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, load_config, setup_logging, version
from .utils import json_serial, sha256sum

DESC_INT_KEYS = ("builddate", "csize", "isize")
DESC_LIST_KEYS = (
    "conflicts",
    "checkdepends",
    "depends",
    "groups",
    "license",
    "makedepends",
    "optdepends",
    "provides",
    "replaces",
)
DESC_STR_KEYS = (
    "arch",
    "base",
    "desc",
    "filename",
    "md5sum",
    "name",
    "packager",
    "pgpsig",
    "sha256sum",
    "url",
    "version",
)

log = logging.getLogger(__name__)


def parse_desc(contents: str) -> dict[str, int | str | list[str]]:
    """
    Parse the content of a desc file and return it as a structured dictionary.

    The desc file typically contains key-value pairs separated by empty newlines.
    Each key is enclosed in percent signs (e.g., %NAME%) and is followed by its value on
    the next line. The value can span multiple lines until the next key is encountered.
    """
    result: dict[str, int | str | list[str]] = {}
    for block in contents.split("\n\n"):
        if block:
            header, _, body = block.partition("\n")
            values = body.split("\n")
            assert header.startswith("%") and header.endswith("%"), "Invalid header"
            key = header[1:-1].lower()
            value: int | str | list[str]
            if key in DESC_LIST_KEYS:
                assert len(values) > 0, f"Expected at least one value for key {key}"
                value = values
            elif key in DESC_INT_KEYS:
                assert len(values) == 1, f"Expected a single-line value for key {key}"
                value = int(values[0])
            else:
                assert key in DESC_STR_KEYS, f"Unexpected key {key}"
                assert len(values) == 1, f"Expected a single-line value for key {key}"
                value = values[0]
            result[key] = value
    return result


def read_pkg_db(file_path: str | Path) -> dict[str, dict[str, int | str | list[str]]]:
    """
    Read the package database from a .db (tar.gz) file and return it as a dictionary.

    Each package is represented by a subdirectory containing a "desc" file.
    The dictionary keys are the package names, and the values are the parsed desc contents.
    """
    packages = {}
    with tarfile.open(file_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and os.path.basename(member.name) == "desc":
                package = os.path.dirname(member.name)
                reader = tar.extractfile(member)
                assert reader is not None, "Failed to extract desc file"
                contents = reader.read().decode("utf-8")
                packages[package] = parse_desc(contents)
    return packages


def compute_changes(
    old_db: dict[str, dict[str, int | str | list[str]]],
    new_db: dict[str, dict[str, int | str | list[str]]],
) -> tuple[list[dict[str, int | str | list[str]]], list[str]]:
    """
    Compute the changes between two package databases.

    """
    additions: list[dict[str, int | str | list[str]]] = []
    deletions: list[str] = []  # List of package ids that were removed

    for pkg, new_desc in new_db.items():
        if pkg not in old_db:
            additions.append({"pkg": pkg, **new_desc})

    for pkg in old_db:
        if pkg not in new_db:
            deletions.append(pkg)

    return additions, deletions


def diff_pkg_db(previous_file: str | Path, current_file: str | Path) -> dict[str, Any]:
    previous_file = Path(previous_file)
    current_file = Path(current_file)
    previous: dict[str, datetime | int | str] = {}
    current: dict[str, datetime | int | str] = {}

    previous_db = read_pkg_db(previous_file)
    current_db = read_pkg_db(current_file)

    previous["modified_at"] = datetime.fromtimestamp(previous_file.stat().st_mtime, UTC)
    current["modified_at"] = datetime.fromtimestamp(current_file.stat().st_mtime, UTC)

    previous["size"] = previous_file.stat().st_size
    current["size"] = current_file.stat().st_size

    # Compute SHA256 checksums (this is fast, ~70 ms for two extra.db)
    previous["sha256sum"] = sha256sum(previous_file)
    current["sha256sum"] = sha256sum(current_file)

    additions, deletions = compute_changes(previous_db, current_db)
    return {
        "previous": previous,
        "current": current,
        "additions": additions,
        "deletions": deletions,
    }


def diff_command(
    file1: str | Path,
    file2: str | Path,
    output_file: str | Path | None = None,
    force: bool = False,
) -> bool:
    log.info("Computing diff between %s and %s", file1, file2)
    if output_file is None:
        output_file = Path(file2).with_suffix(".db.diff.json.zst")
    if Path(output_file).exists() and not force:
        # TODO: Maybe check if files sha256 sums match before warning
        log.warning(
            "Output file %s already exists. Use --force to overwrite.", output_file
        )
        return True
    try:
        changes = diff_pkg_db(file1, file2)
    except (EOFError, tarfile.TarError) as e:
        log.error("Failed to compute diff due to error: %s", e)
        return False

    log.info("Writing diff to %s", output_file)
    with zstd.open(output_file, "wt", level=6) as f:
        json.dump(changes, f, indent=2, default=json_serial, ensure_ascii=False)
    return True


def generate_command(root: str | Path, force: bool = False) -> bool:
    # The archive has the layout: /YYYY/YYYY-MM-DD/YYMMDD.$repo.$arch.db
    # Walk through the archive and generate diffs for each package database
    last_repo_db: dict[str, Path] = {}
    root = Path(root)
    if not root.exists():
        log.error("Archive root %s does not exist", root)
        return False

    log.info("Generating diffs from archive at %s", root)
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir():
            continue
        for date_dir in sorted(year_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            for repo_db in sorted(date_dir.glob("*.db")):
                _, repo, arch = repo_db.stem.split(".")
                repo_key = f"{repo}.{arch}"
                if repo_key in last_repo_db:
                    success = diff_command(last_repo_db[repo_key], repo_db, force=force)
                    if success:
                        # Successfully computed diff, update the last seen repo database
                        last_repo_db[repo_key] = repo_db
                else:
                    try:
                        read_pkg_db(repo_db)
                    except (EOFError, tarfile.TarError) as e:
                        log.error(
                            "Failed to read package database %s due to error: %s",
                            repo_db,
                            e,
                        )
                        continue
                    last_repo_db[repo_key] = repo_db
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute changes between two package databases"
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
        default=DEFAULT_CONFIG,
        help="Path to the configuration file (default: %(default)s)",
    )
    parser.add_argument(
        "-l",
        "--log-config",
        type=str,
        default="default",
        help="Logging configuration to use (default: %(default)s)",
    )
    command = parser.add_subparsers(dest="command")

    diff_parser = command.add_parser(
        "diff", help="Compute changes between two package databases"
    )
    diff_parser.add_argument("file1", help="Path to the previous package database")
    diff_parser.add_argument("file2", help="Path to the current package database")
    diff_parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        help="Path to the output diff file (default: <file2>.db.diff.json.zst)",
    )
    diff_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force recomputation of the diff even if it exists",
    )

    generate_parser = command.add_parser(
        "generate", help="Generate from the archive of package databases"
    )
    generate_parser.add_argument(
        "root", help="Path to the root of the archive of package databases"
    )
    generate_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force recomputation of the generated databases even if they exist",
    )

    args = parser.parse_args()
    return args


def main() -> bool | None:
    args = parse_args()
    config = load_config(args.config)
    logging_config = config["logging"]
    setup_logging(logging_config, key=args.log_config)

    if args.command == "diff":
        return diff_command(
            args.file1, args.file2, output_file=args.output_file, force=args.force
        )
    elif args.command == "generate":
        return generate_command(args.root, force=args.force)
    else:
        log.error("No command specified")
        return False
