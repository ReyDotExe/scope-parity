"""Tests for the pytest plugin, over invented orders/billing registries.

These run pytest inside pytest via the pytester fixture. The plugin
under test is the installed scope_parity entry point, so what runs
here is what a user's suite would load.
"""

import pytest

from scope_parity import Registry, Route, Scope
from scope_parity.pytest_plugin import assert_parity

CLEAN_REGISTRY_MODULE = """\
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

DIRTY_REGISTRY_MODULE = """\
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

WARNING_ONLY_REGISTRY_MODULE = """\
from scope_parity import Registry, Route, Scope

registry = Registry(
    routes=[Route("GET", "/orders", "list_orders", scopes={"orders:read"})],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("billing:refund", "issue refunds"),
    ],
)
"""


def enabled_pyproject(target: str = "parity_registry", extra: str = "") -> str:
    return f'[tool.scope-parity]\ntarget = "{target}"\npytest = true\n{extra}'


def test_plugin_passes_on_a_clean_registry(pytester):
    pytester.makepyfile(parity_registry=CLEAN_REGISTRY_MODULE)
    pytester.makefile(".toml", pyproject=enabled_pyproject())
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*scope-parity*PASSED*"])


def test_plugin_fails_on_a_dirty_registry_and_names_the_findings(pytester):
    pytester.makepyfile(parity_registry=DIRTY_REGISTRY_MODULE)
    pytester.makefile(".toml", pyproject=enabled_pyproject())
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*route-unprotected*delete_order*",
            "*route-unknown-scope*billing:view*",
            "*scope-unused*billing:read*",
            "*2 errors, 1 warning*",
        ]
    )


def test_without_configuration_pytest_is_untouched(pytester):
    pytester.makepyfile(
        test_orders="""
        def test_orders_math():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)
    # the plugins header names scope-parity; what must be absent is the item
    result.stdout.no_fnmatch_line("*scope-parity PASSED*")
    result.stdout.no_fnmatch_line("*scope-parity FAILED*")


def test_target_alone_does_not_opt_in(pytester):
    # The CLI reads target from the same table; configuring the CLI
    # must not silently change the test suite.
    pytester.makepyfile(parity_registry=CLEAN_REGISTRY_MODULE)
    pytester.makefile(
        ".toml", pyproject='[tool.scope-parity]\ntarget = "parity_registry"\n'
    )
    pytester.makepyfile(
        test_orders="""
        def test_orders_math():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)
    result.stdout.no_fnmatch_line("*scope-parity PASSED*")
    result.stdout.no_fnmatch_line("*scope-parity FAILED*")


def test_warnings_do_not_fail_by_default(pytester):
    pytester.makepyfile(parity_registry=WARNING_ONLY_REGISTRY_MODULE)
    pytester.makefile(".toml", pyproject=enabled_pyproject())
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_fail_on_warning_makes_warnings_fail(pytester):
    pytester.makepyfile(parity_registry=WARNING_ONLY_REGISTRY_MODULE)
    pytester.makefile(
        ".toml", pyproject=enabled_pyproject(extra='fail_on = "warning"\n')
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*scope-unused*billing:refund*"])


def test_fail_on_never_reports_without_failing(pytester):
    pytester.makepyfile(parity_registry=DIRTY_REGISTRY_MODULE)
    pytester.makefile(
        ".toml", pyproject=enabled_pyproject(extra='fail_on = "never"\n')
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_invalid_fail_on_fails_the_item(pytester):
    pytester.makepyfile(parity_registry=CLEAN_REGISTRY_MODULE)
    pytester.makefile(
        ".toml", pyproject=enabled_pyproject(extra='fail_on = "sometimes"\n')
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*fail_on*"])


def test_broken_target_fails_like_exit_two(pytester):
    pytester.makefile(".toml", pyproject=enabled_pyproject("no_such_orders_module"))
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["*could not be performed*could not import*no_such_orders_module*"]
    )


def test_empty_registry_fails_like_exit_two(pytester):
    pytester.makepyfile(
        parity_registry="from scope_parity import Registry\n\nregistry = Registry()\n"
    )
    pytester.makefile(".toml", pyproject=enabled_pyproject())
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*contains no routes*not a pass*"])


def test_opt_in_without_target_fails_the_item(pytester):
    pytester.makefile(".toml", pyproject="[tool.scope-parity]\npytest = true\n")
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*target*"])


def test_plugin_item_runs_alongside_ordinary_tests(pytester):
    pytester.makepyfile(parity_registry=DIRTY_REGISTRY_MODULE)
    pytester.makefile(".toml", pyproject=enabled_pyproject())
    pytester.makepyfile(
        test_orders="""
        def test_orders_math():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=1)


def clean_registry() -> Registry:
    return Registry(
        routes=[Route("GET", "/orders", "list_orders", scopes={"orders:read"})],
        scopes=[Scope("orders:read", "view orders")],
    )


def test_assert_parity_passes_and_returns_findings():
    assert assert_parity(clean_registry()) == []


def test_assert_parity_returns_non_failing_findings():
    reg = clean_registry()
    reg.add_scope(Scope("billing:refund", "issue refunds"))
    findings = assert_parity(reg)
    assert [f.code for f in findings] == ["scope-unused"]


def test_assert_parity_fails_and_names_the_findings():
    reg = clean_registry()
    reg.add_route(Route("DELETE", "/orders/{id}", "delete_order"))
    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_parity(reg)
    assert "route-unprotected" in str(excinfo.value)
    assert "delete_order" in str(excinfo.value)


def test_assert_parity_rejects_invalid_fail_on():
    with pytest.raises(ValueError):
        assert_parity(clean_registry(), fail_on="sometimes")
