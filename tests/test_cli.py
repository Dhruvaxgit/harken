"""CLI tests — cover the surface the review found at 0% coverage.

Uses Typer's CliRunner; HTTP is mocked with respx where a command talks to a
live source. `_serve` (which blocks on uvicorn.run) is stubbed out.
"""

import httpx
import respx
from typer.testing import CliRunner

from harken import cli

runner = CliRunner()


def test_demo_and_serve_default_to_the_same_db(tmp_path, monkeypatch):
    # regression test: `demo` used to write to harken-demo.db while `report`
    # and `serve` defaulted to harken.db, so the documented quickstart
    # (harken demo -> harken serve) opened an empty dashboard.
    monkeypatch.chdir(tmp_path)
    seen_dbs = []
    monkeypatch.setattr(cli, "_serve", lambda db, port, host="127.0.0.1": seen_dbs.append(db))

    demo_result = runner.invoke(cli.app, ["demo"])
    assert demo_result.exit_code == 0, demo_result.output

    serve_result = runner.invoke(cli.app, ["serve"])
    assert serve_result.exit_code == 0, serve_result.output

    assert seen_dbs == ["harken.db", "harken.db"]


def test_demo_then_report_share_data_with_no_flags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    demo_result = runner.invoke(cli.app, ["demo", "--no-serve"])
    assert demo_result.exit_code == 0
    assert "No data yet" not in demo_result.output

    report_result = runner.invoke(cli.app, ["report"])
    assert report_result.exit_code == 0
    assert "No data yet" not in report_result.output
    assert "mentions" in report_result.output


def test_demo_dedupes_on_a_second_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(cli.app, ["demo", "--no-serve"])
    first = runner.invoke(cli.app, ["report"])
    runner.invoke(cli.app, ["demo", "--no-serve"])
    second = runner.invoke(cli.app, ["report"])
    assert first.output == second.output  # same totals, not doubled


def test_report_with_no_data_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["report", "--db", str(tmp_path / "empty.db")])
    assert result.exit_code == 1
    assert "No data yet" in result.output


def test_report_closes_the_store_on_the_no_data_exit_path(tmp_path, monkeypatch):
    # regression test: `report` used to raise typer.Exit(1) before reaching
    # store.close() on the "no data yet" path, leaking the sqlite connection.
    from harken.store import Store

    closed = []
    original_close = Store.close
    monkeypatch.setattr(Store, "close", lambda self: (closed.append(True), original_close(self)))

    runner.invoke(cli.app, ["report", "--db", str(tmp_path / "empty.db")])
    assert closed == [True]


@respx.mock
def test_track_exits_nonzero_when_every_source_fails(tmp_path):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(500)
    )
    db = str(tmp_path / "t.db")
    result = runner.invoke(
        cli.app, ["track", "acme", "--sources", "hackernews", "--db", db]
    )
    assert result.exit_code == 1


@respx.mock
def test_track_exits_zero_when_a_source_succeeds(tmp_path):
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    db = str(tmp_path / "t.db")
    result = runner.invoke(
        cli.app, ["track", "acme", "--sources", "hackernews", "--db", db]
    )
    assert result.exit_code == 0


def test_sources_lists_registry():
    result = runner.invoke(cli.app, ["sources"])
    assert result.exit_code == 0
    assert "hackernews" in result.output
    assert "reddit" in result.output


def test_version_flag():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
