# scope-parity

[![ci](https://github.com/ReyDotExe/scope-parity/actions/workflows/ci.yml/badge.svg)](https://github.com/ReyDotExe/scope-parity/actions/workflows/ci.yml)

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
- route-unclassifiable (error): an adapter found the route protected
  by a security scheme but could not determine which scopes it
  requires. only produced in triage mode; the default adapter
  behaviour is to refuse the whole run instead. an error, not a
  warning, because the route is unaccounted for and parity cannot be
  proven while it stays that way.

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
- --triage-unclassifiable: report routes the fastapi adapter cannot
  classify as findings instead of refusing the run. see triage mode
  below. requires the fastapi extra.
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

### triage mode

raising is right for a pipeline and wrong for adoption. pointing the
tool at an existing app with two hundred routes and thirty
unclassifiable ones yields one exception and no report on the other
hundred and seventy, which makes incremental fixing impossible.
triage mode turns each unclassifiable route into a
route-unclassifiable error instead, so the run produces the full
report and the count shrinks as routes get fixed:

```
scope-parity myapp.parity:registry --triage-unclassifiable
```

from a library or a parity module, the same choice is the
on_unclassifiable argument:

```python
registry = from_fastapi(app, scopes=scopes, on_unclassifiable="finding")
```

the escape hatch is deliberately loud. every unclassifiable route is
a printed error, the findings are errors and fail the run under the
default --fail-on, and the summary line carries the count whenever
the mode is on, zero included:

```
7 routes and 3 scopes checked: 2 errors, 1 warning, 2 unclassifiable
```

unclassifiable findings are errors, so they are inside the error
count as well as counted on their own. the json summary always has
the unclassifiable field. what triage mode changes is exit 2 with no
report into exit 1 with a full report; it never turns unclassifiable
routes into a pass.

### supported fastapi versions

the adapter reads fastapi internals, and fastapi 0.141 rewrote them:
included routers stay nested in app.routes and the dependant grew a
different scope layout. the supported range is 0.100 to 0.141, and
the dependency specifier says fastapi>=0.100,<0.142 because a range
this project has not tested is not a range it claims. ci runs the
suite against both sides of the refactor and the boundaries of the
range; the upper bound moves when a new version joins the matrix and
passes.

## the pytest plugin

a separate CI step is easy to forget to add. the plugin runs the
check inside the test suite that already runs, as one extra collected
test named scope-parity. install the extra:

```
pip install -e ".[pytest]"
```

installing changes nothing by itself. the plugin collects its test
only when pyproject.toml asks for it:

```toml
[tool.scope-parity]
target = "myapp.parity:registry"
pytest = true
```

target is the same key the CLI reads, but target alone stays
CLI-only; pytest = true is the explicit opt-in. the policy is the
CLI's, not a second one: fail_on may be set in the same table with
the same values and the same default, findings that meet it fail the
test with a report naming each one, and a run that could not be
performed, a broken target or an empty registry, fails the test the
way the CLI would exit 2.

```
FAILED scope-parity - Failed: scope-parity found:
error    route-unprotected  DELETE /orders/{id} (delete_order) declares no scope ...
```

suites that build the registry themselves, for example around a
fastapi app fixture, can use the assertion helper instead of the
collected test:

```python
from scope_parity.pytest_plugin import assert_parity

def test_scope_parity(app):
    assert_parity(from_fastapi(app, scopes=SCOPES))
```

assert_parity fails the test the same way and returns the findings
list when it passes, so non-failing warnings can still be asserted
on.

## trust boundary

scope-parity imports your application to read its routes, so it runs
module-level code. it is for code you trust, the same as a test
suite. it is not a scanner for untrusted input.

## status

this is stage 4: the data model, the checks, the CLI, the fastapi
adapter with triage mode, the pytest plugin, and CI that tests
python 3.11 to 3.13, the supported fastapi range, and the tool
against its own demo registry in examples/. stage 5, docs and
publishing to pypi, is not built. the core imports nothing outside
the standard library; fastapi and pytest are optional extras, one
for the adapter and one for the plugin.

## license

MIT.
