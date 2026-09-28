"""The checks: pure functions from a Registry to a list of Findings."""

from __future__ import annotations

from scope_parity.model import Finding, Registry, Severity

__all__ = [
    "EXEMPTION_MISSING_REASON",
    "ROUTE_UNCLASSIFIABLE",
    "ROUTE_UNKNOWN_SCOPE",
    "ROUTE_UNPROTECTED",
    "SCOPE_UNUSED",
    "check_exemptions",
    "check_unclassifiable_routes",
    "check_unknown_scopes",
    "check_unprotected_routes",
    "check_unused_scopes",
    "run_checks",
]

ROUTE_UNPROTECTED = "route-unprotected"
SCOPE_UNUSED = "scope-unused"
ROUTE_UNKNOWN_SCOPE = "route-unknown-scope"
EXEMPTION_MISSING_REASON = "exemption-missing-reason"
ROUTE_UNCLASSIFIABLE = "route-unclassifiable"


def check_unprotected_routes(registry: Registry) -> list[Finding]:
    """Report every route that declares no scope and is not marked public.

    A route with a public Exemption is skipped here even if the
    exemption has no reason; check_exemptions reports that case. A
    route marked unclassifiable is also skipped: it is protected by a
    security scheme, so calling it unprotected would be wrong, and
    check_unclassifiable_routes reports it under its own code.
    Returns a list of ERROR findings, one per unprotected route.
    """
    findings: list[Finding] = []
    for route in registry.routes:
        if route.scopes or route.public is not None or route.unclassifiable:
            continue
        findings.append(
            Finding(
                code=ROUTE_UNPROTECTED,
                severity=Severity.ERROR,
                subject=route.subject,
                message=(
                    f"{route.subject} ({route.handler}) declares no scope "
                    "and is not marked public"
                ),
            )
        )
    return findings


def check_unused_scopes(registry: Registry) -> list[Finding]:
    """Report every scope that no route declares and that is not marked routeless.

    Matching is by exact name; a route declaring "orders" does not use
    the scope "orders:read". Returns a list of WARNING findings, one
    per unused scope.
    """
    declared = registry.declared_scope_names()
    findings: list[Finding] = []
    for scope in registry.scopes:
        if scope.name in declared or scope.routeless is not None:
            continue
        findings.append(
            Finding(
                code=SCOPE_UNUSED,
                severity=Severity.WARNING,
                subject=scope.name,
                message=(
                    f"scope {scope.name!r} is not declared by any route "
                    "and is not marked routeless"
                ),
            )
        )
    return findings


def check_unknown_scopes(registry: Registry) -> list[Finding]:
    """Report every scope name a route declares that is registered nowhere.

    This is the usual other half of a half-applied rename: the registry
    gained the new name and the route still declares the old one.
    Returns a list of ERROR findings, one per route and unknown name.
    """
    known = registry.scope_names()
    findings: list[Finding] = []
    for route in registry.routes:
        for name in sorted(route.scopes - known):
            findings.append(
                Finding(
                    code=ROUTE_UNKNOWN_SCOPE,
                    severity=Severity.ERROR,
                    subject=route.subject,
                    message=(
                        f"{route.subject} ({route.handler}) declares scope "
                        f"{name!r}, which is not in the scope registry"
                    ),
                )
            )
    return findings


def check_unclassifiable_routes(registry: Registry) -> list[Finding]:
    """Report every route an adapter marked unclassifiable.

    Such a route is protected by a security scheme, but the adapter
    could not determine which scopes it requires, so parity cannot be
    proven for it. Only adapters running in triage mode produce these
    routes; the default adapter behaviour is to raise instead. Returns
    a list of ERROR findings, one per unclassifiable route.
    """
    findings: list[Finding] = []
    for route in registry.routes:
        if not route.unclassifiable:
            continue
        findings.append(
            Finding(
                code=ROUTE_UNCLASSIFIABLE,
                severity=Severity.ERROR,
                subject=route.subject,
                message=(
                    f"{route.subject} ({route.handler}) carries a security "
                    "scheme but the adapter could not determine its scopes; "
                    "declare them with Security(scheme, scopes=[...]), or "
                    "mark the endpoint with @declares(...) or @public(...)"
                ),
            )
        )
    return findings


def check_exemptions(registry: Registry) -> list[Finding]:
    """Report every exemption whose reason is empty or whitespace.

    An exemption suppresses its underlying finding even without a
    reason, so this check is what keeps a reasonless opt-out from
    passing silently. Returns a list of ERROR findings.
    """
    findings: list[Finding] = []
    for route in registry.routes:
        if route.public is not None and not route.public.has_reason():
            findings.append(
                Finding(
                    code=EXEMPTION_MISSING_REASON,
                    severity=Severity.ERROR,
                    subject=route.subject,
                    message=(
                        f"{route.subject} ({route.handler}) is marked public "
                        "without a reason"
                    ),
                )
            )
    for scope in registry.scopes:
        if scope.routeless is not None and not scope.routeless.has_reason():
            findings.append(
                Finding(
                    code=EXEMPTION_MISSING_REASON,
                    severity=Severity.ERROR,
                    subject=scope.name,
                    message=f"scope {scope.name!r} is marked routeless without a reason",
                )
            )
    return findings


def run_checks(registry: Registry) -> list[Finding]:
    """Run every check over the registry and return all findings.

    The order is stable: unprotected routes, unclassifiable routes,
    unknown scopes, unused scopes, then reasonless exemptions. Returns
    an empty list for a clean registry.
    """
    return [
        *check_unprotected_routes(registry),
        *check_unclassifiable_routes(registry),
        *check_unknown_scopes(registry),
        *check_unused_scopes(registry),
        *check_exemptions(registry),
    ]
