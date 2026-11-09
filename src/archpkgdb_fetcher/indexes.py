import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def iso8601(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def generate_index(directory: Path) -> None:
    entries = []

    with os.scandir(directory) as iterator:
        for entry in iterator:
            # Match Nginx autoindex behavior.
            if entry.name.startswith(".") or entry.name == "index.json":
                continue

            stat = entry.stat(follow_symlinks=False)

            if entry.is_dir(follow_symlinks=False):
                name = entry.name + "/"
                entry_type = "directory"
            elif entry.is_file(follow_symlinks=False):
                name = entry.name
                entry_type = "file"
            else:
                name = entry.name
                entry_type = "other"

            item: dict[str, str | int] = {
                "name": name,
                "type": entry_type,
                "mtime": iso8601(stat.st_mtime),
            }

            if entry_type == "file":
                item["size"] = stat.st_size

            entries.append(item)

    # Directories first, then files, alphabetically.
    entries.sort(key=lambda item: (item["type"] != "directory", item["name"]))

    output = directory / "index.json"

    # Atomic write to avoid serving partially written indexes.
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".index-", suffix=".tmp")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(entries, file, indent=2, ensure_ascii=False)
            file.write("\n")

        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    except BaseException:
        os.unlink(temporary)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recursively generate Nginx-compatible JSON directory indexes."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Root directory (default: current directory)",
    )
    args = parser.parse_args()

    root = args.directory.resolve()

    for directory, subdirectories, _ in os.walk(root, topdown=False):
        path = Path(directory)

        # Do not follow symlink directories.
        subdirectories[:] = [
            name for name in subdirectories if not (path / name).is_symlink()
        ]

        generate_index(path)
