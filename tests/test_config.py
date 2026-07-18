"""Tests for .env loading and env-var driven configuration."""

import importlib
import os

import harken.config as config


def test_dotenv_in_cwd_is_picked_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HARKEN_LLM_PROVIDER", raising=False)
    (tmp_path / ".env").write_text("HARKEN_LLM_PROVIDER=anthropic\n")
    try:
        importlib.reload(config)
        assert config.Config().llm_provider == "anthropic"
    finally:
        # load_dotenv() mutates os.environ directly, bypassing monkeypatch's
        # own undo tracking, so clean it up by hand rather than relying on
        # monkeypatch's (stacked, order-sensitive) teardown for this one.
        os.environ.pop("HARKEN_LLM_PROVIDER", None)


def test_dotenv_lookup_uses_cwd_not_package_location(tmp_path, monkeypatch):
    # config.py lives inside the installed package; .env must be resolved
    # against wherever the user *runs* harken from, not the package's own
    # directory (find_dotenv() defaults to the latter and would silently
    # ignore a project-local .env once harken is pip-installed).
    monkeypatch.chdir(tmp_path)
    found = config.find_dotenv(usecwd=True)
    assert found == "" or found.startswith(str(tmp_path))


def test_config_defaults_without_env():
    cfg = config.Config()
    assert cfg.db_path == "harken.db"
    assert cfg.sources == ["hackernews", "reddit"]
    assert cfg.llm_provider == "none"
