import importlib
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

main_module = importlib.import_module("archpkgdb_fetcher.main")


def test_parse_args_uses_default_config_and_disables_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["archpkgdb-fetcher"])

    args = main_module.parse_args()

    assert args.config == main_module.CONFIG
    assert args.force is False


def test_parse_args_accepts_config_and_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["archpkgdb-fetcher", "--config", "custom.toml", "--force"],
    )

    args = main_module.parse_args()

    assert args.config == "custom.toml"
    assert args.force is True


def test_load_config_reads_toml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[fetcher]\nroot = 'data'\n", encoding="utf-8")

    assert main_module.load_config(config_file) == {"fetcher": {"root": "data"}}


def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.toml"

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        main_module.load_config(missing_file)


def test_main_passes_loaded_configuration_and_force_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "logging": {"version": 1},
        "fetcher": {"root": "data"},
        "servers": [{"url": "https://example.test", "role": "current"}],
    }
    fetch_calls: list[tuple[dict, list[dict], bool, date | None]] = []
    monkeypatch.setattr(
        main_module,
        "parse_args",
        lambda: SimpleNamespace(config="config.toml", force=True, archive_date=None),
    )
    monkeypatch.setattr(main_module, "load_config", lambda _path: config)
    monkeypatch.setattr(main_module, "setup_logging", lambda _config: None)

    def fake_fetcher(
        fetcher_config: dict,
        servers: list[dict],
        force: bool,
        archive_date: date | None,
    ) -> dict:
        fetch_calls.append((fetcher_config, servers, force, archive_date))
        return {}

    monkeypatch.setattr(
        main_module,
        "fetcher",
        fake_fetcher,
    )

    main_module.main()

    assert fetch_calls == [(config["fetcher"], config["servers"], True, None)]
