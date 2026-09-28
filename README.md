# scope-parity

parity checks between a route registry and a permission registry.

the most common authorization defect is not a bypassed check. it is a
route that ships with no check attached: a new endpoint added in a
hurry, the decorator forgotten, and nothing errors because a missing
check looks exactly like working code. scope-parity takes the list of
routes and the list of scopes and reports the mismatches, so CI fails
instead of a human noticing.

## the checks

- route-unprotected (error): a route declares no scope and is not
  marked public.
- route-unknown-scope (error): a route declares a scope name that is
  not in the scope registry. usually the other half of a half-applied
  rename.
- scope-unused (warning): a scope no route declares. often a rename
  that was only half applied, and a sign the route it used to protect
  may now be declaring nothing.
- exemption-missing-reason (error): a route was marked public, or a
  scope routeless, without a reason.

scope names match exactly. ":" is a naming convention, not a
hierarchy. a route declaring "orders" does not satisfy "orders:read",
and the reverse does not hold either. whether one scope implies
another is your authorizer's policy. honoring it here would let a
broad scope mask the renames this tool exists to catch.

exemptions are deliberate and carry a reason. a genuinely public route
gets public=Exemption("..."). a scope that governs a CLI command or a
background job instead of an endpoint gets routeless=Exemption("...").
an exemption with an empty reason is itself a finding.

## usage

```python
from scope_parity import Exemption, Registry, Route, Scope, run_checks

registry = Registry(
    routes=[
        Route("GET", "/orders", "list_orders", scopes={"orders:read"}),
        Route("POST", "/orders", "create_order", scopes={"orders:write"}),
        Route("GET", "/health", "health", public=Exemption("load balancer probe")),
    ],
    scopes=[
        Scope("orders:read", "view orders"),
        Scope("orders:write", "create and edit orders"),
        Scope("billing:export", "export invoices", routeless=Exemption("runs as a batch job")),
    ],
)

for finding in run_checks(registry):
    print(finding.severity.value, finding.code, finding.subject, finding.message)
```

run_checks returns a list of Finding objects and never prints. a
finding has a machine-readable code, a severity, the subject it
concerns, and a message. fail your build if any finding has severity
error, or on any finding at all if you prefer.

## status

this is stage 1: the data model and the checks. there is no CLI, no
framework adapter, and no pytest plugin yet. the core imports nothing
outside the standard library. pytest is the only test dependency.

## license

MIT.
