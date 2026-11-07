# archpkgdb-fetcher

Fetch and maintain local copies of Arch Linux repository database files (`.db`).
The fetcher uses HTTP validators to avoid downloading files that have not
changed, records fetch metadata in a JSON cache, and organizes downloaded files
into timestamped directories.

## Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/) (for the setup commands below)

## Install

Clone the repository, change into its directory, and sync the project
environment:

```sh
uv sync
```

This installs the project and its dependencies in the local environment.

## Run

Run with the included configuration:

```sh
uv run archpkgdb-fetcher
```

Or specify a configuration file:

```sh
uv run archpkgdb-fetcher --config /path/to/archpkgdb-fetcher.toml
```

The `--config` option defaults to `conf/archpkgdb-fetcher.toml`. The `CONFIG`
environment variable can also set the default configuration path; an explicit
`--config` argument takes precedence.

## Configuration

The example configuration is in [`conf/archpkgdb-fetcher.toml`](conf/archpkgdb-fetcher.toml).
Copy it and adjust the `[fetcher]` settings and `[[servers]]` entries for your
needs.

The `[fetcher]` section controls:

- `root`: directory where database snapshots are stored.
- `path`: output path format. The example uses `$repo` and `$arch` as
  placeholders and `strftime` directives for the current UTC time.
- `cache`: path to the JSON file that stores validators and fetch results.
- `archs` and `repos`: architectures and repositories to fetch.
- `user_agent`: HTTP User-Agent sent with requests.

Each `[[servers]]` entry has a `url` and a `role`. URLs can use `$repo` and
`$arch` placeholders. The example also includes archive-server URL templates.
Currently, the fetcher selects entries with the `current` role and uses only
the first matching server; it does not fail over to another server or fetch
from archive-role servers.

The example stores files under `./data/<timestamp>-<architecture>/` and the
cache at `./data/cache.json`. Paths are interpreted relative to the process's
working directory.

## Fetch behavior

For each configured repository and architecture, the fetcher requests the
corresponding `<repo>.db` file. It sends `If-None-Match` and
`If-Modified-Since` when validator values are available in the cache. A
successful changed response is written to a temporary file and then moved into
place; the cache is updated with the result and any returned ETag or
Last-Modified value.

The log reports each repository's status, such as `fetched`, `not_modified`,
or an error status. Logging is configured in the TOML file.

## Development

Run the linter with:

```sh
uv run ruff check
```
