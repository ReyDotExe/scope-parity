"""Pytest plugin: run the scope-parity checks as a collected test.

A separate CI step is easy to forget to add; a test suite is not. When
enabled, this plugin collects one extra test item, named scope-parity,
that loads the configured registry, runs the checks, and fails with a
report naming every finding that meets the failing severity. The
policy is the CLI's, not a second one: the target and semantics of
fail_on are shared with the command line, a run that cannot be
performed (bad target, empty registry) fails the item the same way it
would exit 2, and findings below the failing severity do not fail it.

The plugin is registered under the pytest11 entry point, so it loads
whenever scope-parity is installed, but it does nothing at all unless
asked: it collects its item only when pyproject.toml opts in with

    [tool.scope-parity]
    target = "myapp.parity:registry"
    pytest = true

fail_on may also be set there ("error", the default, "warning", or
"never"), mirroring the CLI flag.

For suites that build the registry themselves, assert_parity(registry)
is an assertion helper with the same failure report and fail_on
semantics, usable inside any ordinary test.
"""

from __future__ import annotations

import io
import sys
import tomllib
from typing import Any

import pytest

from scope_parity.checks import run_checks
from scope_parity.cli import TargetError, _render_human, _should_fail, load_registry
from scope_parity.model import Finding, Registry

__all__ = ["assert_parity"]

_FAIL_ON_VALUES = ("error", "warning", "never")


def _report(findings: list[Finding], registry: Registry) -> str:
    """Render findings the way the CLI does, into a string."""
    buffer = io.StringIO()
    _render_human(findings, registry, buffer)
    return buffer.getvalue().rstrip("\n")


def assert_parity(registry: Registry, fail_on: str = "error") -> list[Finding]:
    """Run the checks over the registry and fail the test on findings.

    fail_on has the CLI's semantics: "error" (the default) fails on any
    error, "warning" fails on any finding, "never" only reports.
    Returns the full findings list when the test does not fail, so a
    caller can assert on the non-failing findings too.
    """
    if fail_on not in _FAIL_ON_VALUES:
        raise ValueError(f"fail_on must be one of {_FAIL_ON_VALUES}, not {fail_on!r}")
    findings = run_checks(registry)
    if _should_fail(findings, fail_on):
        pytest.fail("scope-parity found:\n" + _report(findings, registry), pytrace=False)
    return findings


def _load_settings(config: pytest.Config) -> dict[str, Any] | None:
    """Return the [tool.scope-parity] table from the rootdir pyproject, if any."""
    path = config.rootpath / "pyproject.toml"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError):
        # pyproject.toml exists but cannot be read as configuration;
        # not this plugin's error to report, and without it there is
        # no opt-in, so stay inert.
        return None
    table = data.get("tool", {}).get("scope-parity")
    return table if isinstance(table, dict) else None


class ScopeParityItem(pytest.Item):
    """The one collected test that runs the parity checks."""

    def __init__(self, *, target: Any, fail_on: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target = target
        self._fail_on = fail_on

    def runtest(self) -> None:
        if not isinstance(self._target, str):
            pytest.fail(
                "the scope-parity run could not be performed: pytest = true "
                "is set in [tool.scope-parity] but target is not a string "
                "or is not set",
                pytrace=False,
            )
        if self._fail_on not in _FAIL_ON_VALUES:
            pytest.fail(
                "the scope-parity run could not be performed: "
                f"tool.scope-parity.fail_on must be one of {_FAIL_ON_VALUES}, "
                f"not {self._fail_on!r}",
                pytrace=False,
            )
        root = str(self.config.rootpath)
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            registry = load_registry(self._target)
        except TargetError as exc:
            pytest.fail(
                f"the scope-parity run could not be performed: {exc}", pytrace=False
            )
        if not registry.routes:
            pytest.fail(
                f"the scope-parity run could not be performed: registry at "
                f"{self._target!r} contains no routes; nothing was checked, "
                "so this is not a pass",
                pytrace=False,
            )
        findings = run_checks(registry)
        if _should_fail(findings, self._fail_on):
            pytest.fail(
                "scope-parity found:\n" + _report(findings, registry), pytrace=False
            )

    def reportinfo(self) -> tuple[Any, int | None, str]:
        return self.config.rootpath / "pyproject.toml", None, self.name


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Append the scope-parity item when pyproject.toml opts in."""
    settings = _load_settings(config)
    if settings is None or not settings.get("pytest"):
        return
    items.append(
        ScopeParityItem.from_parent(
            session,
            name="scope-parity",
            target=settings.get("target"),
            fail_on=settings.get("fail_on", "error"),
        )
    )
