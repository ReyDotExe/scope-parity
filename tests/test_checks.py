"""Tests for the scope-parity checks, over an invented orders/billing service."""

from scope_parity import (
    EXEMPTION_MISSING_REASON,
    ROUTE_UNKNOWN_SCOPE,
    ROUTE_UNPROTECTED,
    SCOPE_UNUSED,
    Exemption,
    Finding,
    Registry,
    Route,
    Scope,
    Severity,
    run_checks,
)


def clean_registry() -> Registry:
    """A registry where every route is protected and every scope is used."""
    return Registry(
        routes=[
            Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
            Route("POST", "/orders", "create_order", scopes={"orders:write"}),
            Route("GET", "/invoices", "list_invoices", scopes={"billing:read"}),
        ],
        scopes=[
            Scope("orders:read", "view orders"),
            Scope("orders:write", "create and edit orders"),
            Scope("billing:read", "view invoices"),
        ],
    )


def codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


def test_clean_registry_produces_no_findings():
    assert run_checks(clean_registry()) == []


def test_route_with_no_scope_is_caught():
    reg = clean_registry()
    reg.add_route(Route("DELETE", "/orders/{id}", "delete_order"))
    findings = run_checks(reg)
    assert codes(findings) == [ROUTE_UNPROTECTED]
    finding = findings[0]
    assert finding.severity is Severity.ERROR
    assert finding.subject == "DELETE /orders/{id}"
    assert "delete_order" in finding.message


def test_scope_with_no_route_is_caught():
    reg = clean_registry()
    reg.add_scope(Scope("billing:refund", "issue refunds"))
    findings = run_checks(reg)
    assert codes(findings) == [SCOPE_UNUSED]
    assert findings[0].severity is Severity.WARNING
    assert findings[0].subject == "billing:refund"


def test_public_exemption_with_reason_suppresses_unprotected_route():
    reg = clean_registry()
    reg.add_route(
        Route("GET", "/health", "health", public=Exemption("load balancer probe"))
    )
    assert run_checks(reg) == []


def test_routeless_exemption_with_reason_suppresses_unused_scope():
    reg = clean_registry()
    reg.add_scope(
        Scope(
            "billing:export",
            "export invoices",
            routeless=Exemption("used by the nightly export job, not an endpoint"),
        )
    )
    assert run_checks(reg) == []


def test_public_exemption_without_reason_is_its_own_finding():
    reg = clean_registry()
    reg.add_route(Route("GET", "/health", "health", public=Exemption("")))
    findings = run_checks(reg)
    assert codes(findings) == [EXEMPTION_MISSING_REASON]
    assert findings[0].severity is Severity.ERROR
    assert findings[0].subject == "GET /health"


def test_routeless_exemption_without_reason_is_its_own_finding():
    reg = clean_registry()
    reg.add_scope(Scope("billing:export", "export invoices", routeless=Exemption("   ")))
    findings = run_checks(reg)
    assert codes(findings) == [EXEMPTION_MISSING_REASON]
    assert findings[0].subject == "billing:export"


def test_parent_scope_does_not_satisfy_child_scope():
    # Exact-name matching: declaring "orders" is unrelated to "orders:read".
    reg = Registry(
        routes=[Route("GET", "/orders", "list_orders", scopes={"orders"})],
        scopes=[Scope("orders:read", "view orders")],
    )
    findings = run_checks(reg)
    assert sorted(codes(findings)) == [ROUTE_UNKNOWN_SCOPE, SCOPE_UNUSED]


def test_child_scope_does_not_satisfy_parent_scope():
    reg = Registry(
        routes=[Route("GET", "/orders", "list_orders", scopes={"orders:read"})],
        scopes=[
            Scope("orders", "everything under orders"),
            Scope("orders:read", "view orders"),
        ],
    )
    findings = run_checks(reg)
    assert codes(findings) == [SCOPE_UNUSED]
    assert findings[0].subject == "orders"


def test_route_declaring_unregistered_scope_is_caught():
    reg = clean_registry()
    reg.add_route(Route("POST", "/invoices", "create_invoice", scopes={"billing:write"}))
    findings = run_checks(reg)
    assert codes(findings) == [ROUTE_UNKNOWN_SCOPE]
    assert findings[0].severity is Severity.ERROR
    assert "billing:write" in findings[0].message


def test_empty_registry_does_not_crash():
    assert run_checks(Registry()) == []


def test_registry_with_only_exempt_route_and_no_scopes():
    reg = Registry(
        routes=[Route("GET", "/status", "status", public=Exemption("public status page"))]
    )
    assert run_checks(reg) == []


def test_route_declaring_multiple_scopes():
    reg = Registry(
        routes=[
            Route(
                "POST",
                "/invoices/{id}/refund",
                "refund_invoice",
                scopes={"billing:write", "orders:read"},
            )
        ],
        scopes=[
            Scope("billing:write", "edit billing"),
            Scope("orders:read", "view orders"),
        ],
    )
    assert run_checks(reg) == []


def test_half_applied_rename_is_caught_from_both_sides():
    # The scope was renamed in the registry but the route still declares
    # the old name, and a second route lost its decorator entirely.
    reg = Registry(
        routes=[
            Route("GET", "/orders", "list_orders"),
            Route("GET", "/invoices", "list_invoices", scopes={"billing:view"}),
        ],
        scopes=[Scope("billing:read", "view invoices")],
    )
    findings = run_checks(reg)
    assert sorted(codes(findings)) == [
        ROUTE_UNKNOWN_SCOPE,
        ROUTE_UNPROTECTED,
        SCOPE_UNUSED,
    ]
