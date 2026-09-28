"""Demo registry: a small, clean orders/billing service.

CI runs the scope-parity CLI against this module so the tool is
exercised end to end as a tool, not only through unit tests. It uses
only the core, so it works without any extra installed:

    scope-parity examples.demo_registry
"""

from scope_parity import Exemption, Registry, Route, Scope

registry = Registry(
    routes=[
        Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
        Route("POST", "/orders", "create_order", scopes={"orders:write"}),
        Route("GET", "/invoices", "list_invoices", scopes={"billing:read"}),
        Route("GET", "/health", "health", public=Exemption("load balancer probe")),
    ],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("orders:write", "create and edit orders"),
        Scope("billing:read", "view invoices"),
        Scope(
            "billing:export",
            "export invoices",
            routeless=Exemption("runs as a nightly batch job, not an endpoint"),
        ),
    ],
)
