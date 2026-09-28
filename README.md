# scope-parity

parity checks between a route registry and a permission registry.

the most common authorization defect is not a bypassed check. it is a
route that ships with no check attached: a new endpoint added in a
hurry, the decorator forgotten, and nothing errors because a missing
check looks exactly like working code. scope-parity takes the list of
routes and the list of scopes and reports the mismatches, so CI fails
instead of a human noticing.

## install

not on pypi yet. clone the repository and install it into your
environment:

```
git clone https://github.com/ReyDotExe/scope-parity.git
cd scope-parity
pip install -e .
```

python 3.11 or newer. no runtime dependencies.

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

## the cli

point scope-parity at the module that holds your registry:

```
scope-parity myapp.scopes:registry
```

the part after the colon is an attribute name and defaults to
registry, so `scope-parity myapp.scopes` means the same thing. the
attribute must be a Registry, or a zero-argument callable that
returns one. the current directory goes on sys.path first, so the
command works from a repo root without installing your application.
instead of an argument, the target can live in pyproject.toml:

```toml
[tool.scope-parity]
target = "myapp.scopes:registry"
```

what a run with findings prints:

```
error    route-unprotected    DELETE /orders/{id} (delete_order) declares no scope and is not marked public
error    route-unknown-scope  GET /invoices (list_invoices) declares scope 'billing:view', which is not in the scope registry
warning  scope-unused         scope 'billing:read' is not declared by any route and is not marked routeless

4 routes and 3 scopes checked: 2 errors, 1 warning
```

errors sort before warnings, and the summary line prints on clean
runs too, so a step that produced no output is never confused with
one that did not run. severities are coloured when stdout is a
terminal, never when piped or redirected, and NO_COLOR is honored.

the flags:

- --fail-on {error,warning,never}: the lowest severity that makes
  the run exit 1. error is the default; warnings print but do not
  fail. warning fails on any finding. never reports without failing.
- --format {human,json}: json prints one document with every finding
  (code, severity, subject, message) and the summary counts, for CI
  to consume.
- --version.

the exit codes:

- 0: the checks ran and no finding met the failing severity.
- 1: the checks ran and at least one finding met it.
- 2: the run could not be performed. bad arguments, a target that
  did not import, an attribute that is missing or not a Registry, or
  a registry with no routes. an import error is not a clean run, and
  neither is an empty registry: a run that checked nothing must not
  look like a pass.

## the fastapi adapter

hand-writing a registry that mirrors your real routes is itself a
defect waiting to happen: the mirror drifts from the app, and a
checker reading a stale mirror reports a clean run on an app that
changed. the adapter removes the duplication by reading the routes
from the live app object. the scope registry stays hand-written,
because it is the source of truth the app is checked against;
inferring it from what the routes declare would leave scope-unused
and route-unknown-scope with nothing to catch.

install the extra:

```
pip install -e ".[fastapi]"
```

write a small module that builds the registry from your app, and
point the CLI at it:

```python
from scope_parity import Scope
from scope_parity.fastapi import from_fastapi

from myapp.main import app

registry = from_fastapi(app, scopes=[
    Scope("orders:read", "view orders"),
    Scope("orders:write", "create and edit orders"),
])
```

```
scope-parity myapp.parity:registry
```

the adapter reads scopes from the same security dependency tree
fastapi's openapi generator reads: Security(scheme, scopes=[...])
declared as a parameter, in a route's dependencies, or in a router's
dependencies, which apply to everything mounted under the router,
included sub-routers too. two markers cover apps that authorize some
other way: @declares("orders:read") on an endpoint adds scopes, and
@public("reason") marks it deliberately public and becomes the
route's exemption. plain Depends() is not treated as authorization:
the adapter cannot tell a database session from a hand-rolled auth
check, so a route whose only protection is a plain dependency needs
a marker.

a route the adapter cannot classify, one that carries a security
scheme but declares no scope anywhere, is neither reported as
unprotected nor waved through. from_fastapi raises instead, naming
every such route and how to resolve it, and through the CLI that is
exit code 2: the run could not be performed. this is the same
distinction the empty-registry exit code draws.

routes that are not fastapi api routes, such as the documentation
routes and starlette mounts, are outside the adapter and skipped.

## trust boundary

scope-parity imports your application to read its routes, so it runs
module-level code. it is for code you trust, the same as a test
suite. it is not a scanner for untrusted input.

## status

this is stage 3: the data model, the checks, the CLI, and a fastapi
adapter. the pytest plugin and canned CI config are still not built.
the core imports nothing outside the standard library; fastapi is an
optional extra used only by the adapter. pytest and fastapi are the
test dependencies.

## license

MIT.
