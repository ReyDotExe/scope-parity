"""Tests for the CLI, over invented orders/billing fixture modules."""

import json

import pytest

from scope_parity.cli import (
    EXIT_CLEAN,
    EXIT_FINDINGS,
    EXIT_TOOL_FAILURE,
    main,
)

CLEAN_MODULE = """\
from scope_parity import Registry, Route, Scope

registry = Registry(
    routes=[
        Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
        Route("POST", "/orders", "create_order", scopes={"orders:write"}),
    ],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("orders:write", "create and edit orders"),
    ],
)
"""

DIRTY_MODULE = """\
from scope_parity import Registry, Route, Scope

registry = Registry(
    routes=[
        Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
        Route("DELETE", "/orders/{id}", "delete_order"),
        Route("GET", "/invoices", "list_invoices", scopes={"billing:view"}),
    ],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("billing:read", "view invoices"),
    ],
)
"""

WARNING_ONLY_MODULE = """\
from scope_parity import Registry, Route, Scope

registry = Registry(
    routes=[
        Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
    ],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("billing:refund", "issue refunds"),
    ],
)
"""

FACTORY_MODULE = """\
from scope_parity import Registry, Route, Scope

def build():
    return Registry(
        routes=[Route("GET", "/orders", "list_orders", scopes={"orders:read"})],
        scopes=[Scope("orders:read", "view orders")],
    )
"""

EMPTY_MODULE = """\
from scope_parity import Registry

registry = Registry()
"""


@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    """A directory on sys.path that tests write fixture modules into."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def write_module(fixture_dir, name: str, source: str) -> str:
    """Write a fixture module and return its (unique) module name."""
    (fixture_dir / f"{name}.py").write_text(source, encoding="utf-8")
    return name


def test_clean_registry_exits_clean(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_clean", CLEAN_MODULE)
    assert main([f"{name}:registry"]) == EXIT_CLEAN
    out = capsys.readouterr().out
    assert "2 routes and 2 scopes checked: no findings" in out


def test_error_findings_exit_with_failing_code(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_dirty", DIRTY_MODULE)
    assert main([f"{name}:registry"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "route-unprotected" in out
    assert "route-unknown-scope" in out
    assert "scope-unused" in out
    assert "2 errors, 1 warning" in out


def test_errors_print_before_warnings(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_order", DIRTY_MODULE)
    main([f"{name}:registry"])
    out = capsys.readouterr().out
    assert out.index("route-unknown-scope") < out.index("scope-unused")


def test_warnings_do_not_fail_by_default(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_warn", WARNING_ONLY_MODULE)
    assert main([f"{name}:registry"]) == EXIT_CLEAN
    out = capsys.readouterr().out
    assert "scope-unused" in out
    assert "0 errors, 1 warning" in out


def test_fail_on_warning_makes_warnings_fail(fixture_dir):
    name = write_module(fixture_dir, "ordersapp_warn2", WARNING_ONLY_MODULE)
    assert main([f"{name}:registry", "--fail-on", "warning"]) == EXIT_FINDINGS


def test_fail_on_never_reports_without_failing(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_dirty2", DIRTY_MODULE)
    assert main([f"{name}:registry", "--fail-on", "never"]) == EXIT_CLEAN
    assert "route-unprotected" in capsys.readouterr().out


def test_attribute_defaults_to_registry(fixture_dir):
    name = write_module(fixture_dir, "ordersapp_default", CLEAN_MODULE)
    assert main([name]) == EXIT_CLEAN


def test_bad_module_path_exits_tool_failure(fixture_dir, capsys):
    assert main(["no_such_orders_module:registry"]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "no_such_orders_module" in err
    assert "could not import" in err


def test_module_that_raises_on_import_exits_tool_failure(fixture_dir, capsys):
    name = write_module(
        fixture_dir, "ordersapp_broken", 'raise RuntimeError("db not configured")\n'
    )
    assert main([f"{name}:registry"]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "db not configured" in err


def test_missing_attribute_exits_tool_failure(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_noattr", CLEAN_MODULE)
    assert main([f"{name}:no_such_registry"]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "no_such_registry" in err


def test_attribute_that_is_not_a_registry_exits_tool_failure(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_wrongtype", "registry = 42\n")
    assert main([f"{name}:registry"]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "not a scope_parity.Registry" in err


def test_callable_returning_registry_is_accepted(fixture_dir):
    name = write_module(fixture_dir, "ordersapp_factory", FACTORY_MODULE)
    assert main([f"{name}:build"]) == EXIT_CLEAN


def test_empty_registry_is_not_a_pass(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_empty", EMPTY_MODULE)
    assert main([f"{name}:registry"]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "contains no routes" in err


def test_no_arguments_and_no_pyproject_exits_tool_failure(fixture_dir, capsys):
    assert main([]) == EXIT_TOOL_FAILURE
    err = capsys.readouterr().err
    assert "usage:" in err
    assert "no target" in err


def test_target_read_from_pyproject(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_toml", CLEAN_MODULE)
    (fixture_dir / "pyproject.toml").write_text(
        f'[tool.scope-parity]\ntarget = "{name}:registry"\n', encoding="utf-8"
    )
    assert main([]) == EXIT_CLEAN
    assert "no findings" in capsys.readouterr().out


def test_json_output_contains_every_field_of_every_finding(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_json", DIRTY_MODULE)
    assert main([f"{name}:registry", "--format", "json"]) == EXIT_FINDINGS
    document = json.loads(capsys.readouterr().out)
    assert len(document["findings"]) == 3
    for finding in document["findings"]:
        assert set(finding) == {"code", "severity", "subject", "message"}
        assert finding["code"]
        assert finding["severity"] in {"error", "warning"}
        assert finding["subject"]
        assert finding["message"]
    assert document["summary"] == {
        "errors": 2,
        "warnings": 1,
        "routes": 3,
        "scopes": 2,
    }


def test_no_color_codes_when_stdout_is_not_a_tty(fixture_dir, capsys):
    name = write_module(fixture_dir, "ordersapp_nocolor", DIRTY_MODULE)
    main([f"{name}:registry"])
    assert "\x1b[" not in capsys.readouterr().out


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "scope-parity" in capsys.readouterr().out
