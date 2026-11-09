import argparse
import json
import logging
from compression import zstd
from importlib.resources import files
from pathlib import Path
from typing import Any

from .config import find_config_file, load_config, setup_logging, version

log = logging.getLogger(__name__)


def read_diff(file: Path) -> dict[str, Any]:
    with zstd.open(file, "rt") as f:
        diff = json.load(f)
        assert isinstance(diff, dict)
        return diff


def summarize_diff(diff: dict[str, Any]) -> dict[str, Any]:
    previous = diff["previous"]
    current = diff["current"]
    added = diff["added"]
    removed = diff["removed"]
    packages = {}

    for desc in added.values():
        packages[desc["name"]] = [None, desc["version"]]

    for desc in removed.values():
        if desc["name"] in packages:
            packages[desc["name"]][0] = desc["version"]
        else:
            packages[desc["name"]] = [desc["version"], None]
    return {"previous": previous, "current": current, "packages": packages}


def load_template(template_name: str) -> str:
    resource = files("archpkgdb_fetcher.data").joinpath(template_name)
    with resource.open("r", encoding="utf-8") as f:
        return f.read()


def render_template(template: str, context: dict[str, Any]) -> str:
    for key, value in context.items():
        template = template.replace(f"{{{{ {key} }}}}", str(value))
    return template


def generate_summaries(path: Path, date: str | None = None) -> None:
    # For now, assume date is the path name
    if date is None:
        date = path.name

    log.debug("Generating summaries for path: %s, date: %s", path, date)

    diffs = []
    for diff_file in sorted(path.glob("*.db.diff.json.zst")):
        # format: <timestamp>.<repo>.<arch>.db.diff.json.zst
        _, repo, arch, *_ = diff_file.stem.split(".")
        summary = {
            "diff": diff_file.name,
            "repo": repo,
            "arch": arch,
            **summarize_diff(read_diff(diff_file)),
        }
        try:
            if summary["previous"]["sha256sum"] == summary["current"]["sha256sum"]:
                log.debug("Skipping unchanged diff: %s", diff_file)
                continue
        except KeyError:
            log.warning("Missing sha256sum in diff: %s", diff_file)
        diffs.append(summary)

    if diffs:
        json_summary = json.dumps(diffs, indent=2, ensure_ascii=False)

        template = load_template("summary.html")
        output = render_template(template, {"data": json_summary, "date": date})
        output_file = path / f"summary.html"

        log.info("Writing summary to %s", output_file)
        with open(output_file, "wt", encoding="utf-8") as output_stream:
            output_stream.write(output)
    else:
        log.info("No diffs found for %s", path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate repository change summaries")
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
        default=find_config_file(),
        help="Path to the configuration file (default: %(default)s)",
    )
    parser.add_argument(
        "-l",
        "--log-config",
        type=str,
        default="default",
        help="Logging configuration to use (default: %(default)s)",
    )
    parser.add_argument(
        "directory", type=Path, help="Root directory for generating summaries"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively process directories"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    logging_config = config["logging"]
    setup_logging(logging_config, key=args.log_config)

    root = args.directory.resolve()
    log.debug("Root directory resolved to: %s", root)

    if args.recursive:
        # Find all parent directories containing .db.diff.json.zst files
        for subdir in {path.parent for path in root.rglob("*.db.diff.json.zst")}:
            generate_summaries(subdir)
    else:
        generate_summaries(root)
