"""scope-parity: parity checks between a route registry and a scope registry.

The library takes a Registry of Route and Scope objects and returns
Finding objects describing the mismatches. It never prints; rendering
is left to callers.
"""

__version__ = "0.3.0"

from scope_parity.checks import (
    EXEMPTION_MISSING_REASON,
    ROUTE_UNKNOWN_SCOPE,
    ROUTE_UNPROTECTED,
    SCOPE_UNUSED,
    check_exemptions,
    check_unknown_scopes,
    check_unprotected_routes,
    check_unused_scopes,
    run_checks,
)
from scope_parity.model import Exemption, Finding, Registry, Route, Scope, Severity

__all__ = [
    "EXEMPTION_MISSING_REASON",
    "ROUTE_UNKNOWN_SCOPE",
    "ROUTE_UNPROTECTED",
    "SCOPE_UNUSED",
    "Exemption",
    "Finding",
    "Registry",
    "Route",
    "Scope",
    "Severity",
    "__version__",
    "check_exemptions",
    "check_unknown_scopes",
    "check_unprotected_routes",
    "check_unused_scopes",
    "run_checks",
]
