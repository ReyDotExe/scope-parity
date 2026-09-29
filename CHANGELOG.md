# changelog

notable changes to scope-parity, in the format of
[keep a changelog](https://keepachangelog.com/en/1.1.0/). the project
follows [semantic versioning](https://semver.org/).

1.0.0 is the first version published to pypi. the versions below it
were development milestones: the version number was bumped in the
source at each stage, but nothing was released, so those entries
carry the date the work landed on main and are marked unreleased.
they are kept because the history is real and a user reading old
code or old commits may meet those version numbers.

## [1.0.0] - 2026-09-28

the first published release. no library behaviour changed relative
to 0.4.0; what a 0.4.0 checkout computed, 1.0.0 computes.

### added

- publishing to pypi, through a tag-triggered workflow that uses
  trusted publishing (oidc) instead of a stored api token, and that
  refuses to publish unless the full test suite and the fastapi
  version matrix passed on the tagged commit.
- a weekly scheduled job that installs the newest fastapi regardless
  of the version cap, runs the suite against it, and opens an issue
  with the result, so the cap is re-examined instead of quietly going
  stale.
- this changelog, and a security policy in SECURITY.md.

### changed

- the readme installs from pypi instead of a clone, links the
  changelog and the security policy, and states that
  --triage-unclassifiable only affects from_fastapi calls that did
  not pass on_unclassifiable themselves.

## [0.4.0] - 2026-09-28 (unreleased)

### added

- triage mode: on_unclassifiable="finding" on from_fastapi, the
  triage_unclassifiable() context manager, and the cli flag
  --triage-unclassifiable. routes the adapter cannot classify become
  route-unclassifiable errors in a full report instead of one
  exception and no report, so an existing app can be adopted
  incrementally. the summary line and the json summary carry the
  unclassifiable count.
- a pytest plugin: with pytest = true under [tool.scope-parity], the
  suite collects one extra test named scope-parity that runs the
  checks with the cli's target and fail_on semantics. assert_parity()
  does the same inside a test that builds its own registry.
- ci gained a fastapi version matrix covering the claimed range,
  including both sides of the 0.141 internals refactor, and a
  self-check job that runs the cli against the demo registries and
  asserts the exit codes.

### changed

- the fastapi dependency is capped at the last version the matrix
  has passed against: fastapi>=0.100,<0.142. a range the project has
  not tested is not a range it claims.

## [0.3.0] - 2026-09-28 (unreleased)

### added

- the fastapi adapter, as the optional extra scope-parity[fastapi]:
  from_fastapi(app, scopes) builds a registry from the live app, so
  the route list cannot drift from the application. scopes are read
  from the security dependency tree, the same signals openapi
  generation reads; the @declares() and @public() markers cover apps
  that authorize some other way.
- UnclassifiableRouteError: a route that carries a security scheme
  but declares no scope is neither reported as unprotected nor waved
  through; from_fastapi raises, naming every such route. through the
  cli that is exit code 2.

## [0.2.0] - 2026-09-28 (unreleased)

### added

- the scope-parity command line: point it at module.path[:attribute]
  or set target under [tool.scope-parity] in pyproject.toml. human
  output with a summary line that prints on clean runs too, --format
  json for ci, --fail-on to pick the failing severity, and colour
  only on a terminal with NO_COLOR honored.
- the exit code contract: 0 for a clean run, 1 for findings that
  meet the failing severity, 2 when the run could not be performed,
  including an empty registry, because a run that checked nothing
  must not look like a pass.

## [0.1.0] - 2026-09-27 (unreleased)

### added

- the data model: Route, Scope, Exemption with a mandatory reason,
  Registry, Finding, Severity.
- the checks, as pure functions returning findings: route-unprotected
  and route-unknown-scope as errors, scope-unused as a warning,
  exemption-missing-reason as an error, and run_checks over all of
  them. scope names match exactly; ":" is a naming convention, not a
  hierarchy.

[1.0.0]: https://github.com/ReyDotExe/scope-parity/releases/tag/v1.0.0
