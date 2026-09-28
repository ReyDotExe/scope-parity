"""Tests for the FastAPI adapter, over an invented orders/billing app."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import APIRouter, Depends, FastAPI, Security
from fastapi.security import HTTPBearer, OAuth2PasswordBearer

from scope_parity import (
    ROUTE_UNPROTECTED,
    SCOPE_UNUSED,
    Registry,
    Route,
    Scope,
    Severity,
    run_checks,
)
from scope_parity.fastapi import (
    UnclassifiableRouteError,
    declares,
    from_fastapi,
    public,
)

oauth2 = OAuth2PasswordBearer(tokenUrl="token", scopes={})

SCOPES = [
    Scope("orders:read", "view orders"),
    Scope("orders:write", "create and edit orders"),
    Scope("billing:read", "view invoices"),
    Scope("ops:metrics", "read service metrics"),
]


def build_app() -> FastAPI:
    """An orders/billing app exercising every declaration mechanism."""
    app = FastAPI()

    @app.get("/orders", dependencies=[Security(oauth2, scopes=["orders:read"])])
    def list_orders(): ...

    @app.post("/orders")
    def create_order(token: str = Security(oauth2, scopes=["orders:write"])): ...

    @app.get("/metrics")
    @declares("ops:metrics")
    def metrics(): ...

    @app.get("/health")
    @public("load balancer probe")
    def health(): ...

    @app.get("/open")
    def open_route(): ...

    billing = APIRouter(
        prefix="/billing", dependencies=[Security(oauth2, scopes=["billing:read"])]
    )

    @billing.get("/invoices")
    def list_invoices(): ...

    reports = APIRouter(prefix="/reports")

    @reports.get("/monthly")
    def monthly(): ...

    billing.include_router(reports)
    app.include_router(billing)
    return app


def by_subject(registry: Registry) -> dict[str, Route]:
    return {route.subject: route for route in registry.routes}


def test_registry_contains_exactly_the_api_routes():
    registry = from_fastapi(build_app(), scopes=SCOPES)
    assert sorted(r.subject for r in registry.routes) == [
        "GET /billing/invoices",
        "GET /billing/reports/monthly",
        "GET /health",
        "GET /metrics",
        "GET /open",
        "GET /orders",
        "POST /orders",
    ]


def test_security_in_route_dependencies_yields_scopes():
    route = by_subject(from_fastapi(build_app(), scopes=SCOPES))["GET /orders"]
    assert route.scopes == {"orders:read"}


def test_security_as_parameter_yields_scopes():
    route = by_subject(from_fastapi(build_app(), scopes=SCOPES))["POST /orders"]
    assert route.scopes == {"orders:write"}


def test_declares_marker_yields_scopes():
    route = by_subject(from_fastapi(build_app(), scopes=SCOPES))["GET /metrics"]
    assert route.scopes == {"ops:metrics"}


def test_public_marker_becomes_exemption():
    route = by_subject(from_fastapi(build_app(), scopes=SCOPES))["GET /health"]
    assert route.public is not None
    assert route.public.reason == "load balancer probe"
    assert route.scopes == frozenset()


def test_router_level_dependency_protects_mounted_routes():
    routes = by_subject(from_fastapi(build_app(), scopes=SCOPES))
    assert routes["GET /billing/invoices"].scopes == {"billing:read"}
    assert routes["GET /billing/reports/monthly"].scopes == {"billing:read"}


def test_unprotected_route_has_no_scopes_and_no_exemption():
    route = by_subject(from_fastapi(build_app(), scopes=SCOPES))["GET /open"]
    assert route.scopes == frozenset()
    assert route.public is None


def test_checks_over_the_adapter_registry():
    registry = from_fastapi(build_app(), scopes=SCOPES)
    findings = run_checks(registry)
    assert [(f.code, f.subject) for f in findings] == [
        (ROUTE_UNPROTECTED, "GET /open")
    ]
    assert findings[0].severity is Severity.ERROR


def test_unused_scope_still_caught_against_live_routes():
    registry = from_fastapi(
        build_app(), scopes=[*SCOPES, Scope("billing:refund", "issue refunds")]
    )
    findings = run_checks(registry)
    assert (SCOPE_UNUSED, "billing:refund") in [(f.code, f.subject) for f in findings]


def test_scheme_without_scopes_is_unclassifiable_not_unprotected():
    app = FastAPI()

    @app.get("/admin", dependencies=[Depends(HTTPBearer())])
    def admin(): ...

    with pytest.raises(UnclassifiableRouteError) as excinfo:
        from_fastapi(app, scopes=[])
    assert excinfo.value.subjects == ["GET /admin"]
    message = str(excinfo.value)
    assert "could not classify" in message
    assert "GET /admin" in message
    assert "@declares" in message


def test_unclassifiable_error_lists_every_route():
    app = FastAPI()

    @app.get("/a", dependencies=[Depends(HTTPBearer())])
    def a(): ...

    @app.get("/b", dependencies=[Security(oauth2)])
    def b(): ...

    with pytest.raises(UnclassifiableRouteError) as excinfo:
        from_fastapi(app, scopes=[])
    assert sorted(excinfo.value.subjects) == ["GET /a", "GET /b"]


def test_marker_resolves_an_otherwise_unclassifiable_route():
    app = FastAPI()

    @app.get("/admin", dependencies=[Depends(HTTPBearer())])
    @declares("ops:admin")
    def admin(): ...

    registry = from_fastapi(app, scopes=[Scope("ops:admin")])
    assert by_subject(registry)["GET /admin"].scopes == {"ops:admin"}


def test_declares_requires_at_least_one_scope():
    with pytest.raises(ValueError):
        declares()


def test_docs_routes_are_not_in_the_registry():
    registry = from_fastapi(build_app(), scopes=SCOPES)
    assert not any(r.path.startswith("/docs") for r in registry.routes)
    assert not any(r.path == "/openapi.json" for r in registry.routes)
