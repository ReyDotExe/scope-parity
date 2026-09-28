"""Command-line interface: load a registry, run the checks, report, exit.

The CLI is the only module that prints. It imports the user's code to
find a Registry, hands it to run_checks, renders the findings in a
human or JSON format, and exits with a code a CI system can act on:

    0  the run was performed and no finding met the failing severity
    1  the run was performed and at least one finding met it
    2  the run could not be performed (bad arguments, import failure,
       no Registry at the target, or a registry with no routes)
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Sequence
from typing import TextIO

from scope_parity import __version__
from scope_parity.checks import run_checks
from scope_parity.model import Finding, Registry, Severity

__all__ = ["EXIT_CLEAN", "EXIT_FINDINGS", "EXIT_TOOL_FAILURE", "load_registry", "main"]

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_TOOL_FAILURE = 2

DEFAULT_ATTRIBUTE = "registry"

_EPILOG = """\
target:
  A module path with an optional attribute name, e.g. "myapp.scopes"
  or "myapp.scopes:registry". The attribute defaults to "registry" and
  must be a scope_parity.Registry or a zero-argument callable that
  returns one. The current directory is added to sys.path first. When
  no target is given on the command line, the CLI reads "target" from
  the [tool.scope-parity] table of ./pyproject.toml.

exit codes:
  0  no finding at or above the failing severity
  1  at least one finding at or above the failing severity
  2  the run could not be performed: bad arguments, the target failed
     to import, the attribute is missing or not a Registry, or the
     registry contains no routes
"""


class TargetError(Exception):
    """The registry target could not be resolved to a usable Registry."""


def _split_target(target: str) -> tuple[str, str]:
    """Split "module.path:attr" into its parts, defaulting the attribute."""
    module_path, sep, attribute = target.partition(":")
    if not module_path or (sep and not attribute):
        raise TargetError(
            f"invalid target {target!r}: expected module.path or module.path:attribute"
        )
    return module_path, attribute or DEFAULT_ATTRIBUTE


def load_registry(target: str) -> Registry:
    """Import the target and return the Registry it names.

    Raises TargetError if the module cannot be imported, the attribute
    does not exist, or the attribute is neither a Registry nor a
    zero-argument callable returning one.
    """
    module_path, attribute = _split_target(target)
    try:
        module = importlib.import_module(module_path)
    except BaseException as exc:  # the user's module can raise anything
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise TargetError(
            f"could not import {module_path!r}: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        obj = getattr(module, attribute)
    except AttributeError:
        raise TargetError(
            f"module {module_path!r} has no attribute {attribute!r}"
        ) from None
    if callable(obj) and not isinstance(obj, Registry):
        try:
            obj = obj()
        except Exception as exc:
            raise TargetError(
                f"calling {module_path}:{attribute} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    if not isinstance(obj, Registry):
        raise TargetError(
            f"{module_path}:{attribute} is {type(obj).__name__}, "
            "not a scope_parity.Registry"
        )
    return obj


def _target_from_pyproject() -> str | None:
    """Return the target configured in ./pyproject.toml, if any."""
    import tomllib

    try:
        with open("pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise TargetError(f"could not read pyproject.toml: {exc}") from exc
    target = data.get("tool", {}).get("scope-parity", {}).get("target")
    if target is not None and not isinstance(target, str):
        raise TargetError("tool.scope-parity.target in pyproject.toml must be a string")
    return target


def _use_color(stream: TextIO) -> bool:
    """Return True if severity tokens should be coloured on this stream."""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


_COLORS = {Severity.ERROR: "\x1b[31m", Severity.WARNING: "\x1b[33m"}
_RESET = "\x1b[0m"


def _render_human(
    findings: list[Finding], registry: Registry, stream: TextIO
) -> None:
    """Print one finding per line, errors first, then a summary line."""
    color = _use_color(stream)
    ordered = sorted(findings, key=lambda f: 0 if f.severity is Severity.ERROR else 1)
    code_width = max((len(f.code) for f in ordered), default=0)
    for finding in ordered:
        severity = f"{finding.severity.value:<7}"
        if color:
            severity = f"{_COLORS[finding.severity]}{severity}{_RESET}"
        print(f"{severity}  {finding.code:<{code_width}}  {finding.message}", file=stream)
    errors = sum(1 for f in findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity is Severity.WARNING)
    if findings:
        print(file=stream)
    counts = "no findings" if not findings else (
        f"{errors} error{'s' if errors != 1 else ''}, "
        f"{warnings} warning{'s' if warnings != 1 else ''}"
    )
    print(
        f"{len(registry.routes)} routes and {len(registry.scopes)} scopes "
        f"checked: {counts}",
        file=stream,
    )


def _render_json(
    findings: list[Finding], registry: Registry, stream: TextIO
) -> None:
    """Print one JSON document with every finding and the summary."""
    document = {
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.value,
                "subject": f.subject,
                "message": f.message,
            }
            for f in findings
        ],
        "summary": {
            "errors": sum(1 for f in findings if f.severity is Severity.ERROR),
            "warnings": sum(1 for f in findings if f.severity is Severity.WARNING),
            "routes": len(registry.routes),
            "scopes": len(registry.scopes),
        },
    }
    json.dump(document, stream, indent=2)
    print(file=stream)


def _should_fail(findings: list[Finding], fail_on: str) -> bool:
    """Return True if the findings meet the configured failing severity."""
    if fail_on == "never":
        return False
    if fail_on == "warning":
        return bool(findings)
    return any(f.severity is Severity.ERROR for f in findings)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scope-parity",
        description="Run the scope-parity checks over a route/scope registry.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="registry to check, as module.path[:attribute] "
        "(default attribute: registry)",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "warning", "never"],
        default="error",
        help="lowest severity that makes the run exit 1; 'warning' fails on "
        "any finding, 'never' reports without failing (default: error)",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="output format (default: human)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the scope-parity console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        target = args.target
        if target is None:
            target = _target_from_pyproject()
        if target is None:
            parser.print_usage(sys.stderr)
            print(
                "scope-parity: error: no target given and no tool.scope-parity."
                "target in pyproject.toml",
                file=sys.stderr,
            )
            return EXIT_TOOL_FAILURE
        registry = load_registry(target)
    except TargetError as exc:
        print(f"scope-parity: error: {exc}", file=sys.stderr)
        return EXIT_TOOL_FAILURE

    if not registry.routes:
        print(
            f"scope-parity: error: registry at {target!r} contains no routes; "
            "nothing was checked, so this is not a pass",
            file=sys.stderr,
        )
        return EXIT_TOOL_FAILURE

    findings = run_checks(registry)
    if args.format == "json":
        _render_json(findings, registry, sys.stdout)
    else:
        _render_human(findings, registry, sys.stdout)
    return EXIT_FINDINGS if _should_fail(findings, args.fail_on) else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
