"""Demo registry with deliberate defects.

CI runs the CLI against this module and requires exit code 1, so a
build of the tool that stops reporting anything cannot pass its own
pipeline. One route lost its scope, one declares a name the registry
does not know, and one scope protects nothing.
"""

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
