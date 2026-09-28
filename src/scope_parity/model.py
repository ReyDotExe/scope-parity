"""Data model: routes, scopes, exemptions, the registry, and findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = ["Exemption", "Finding", "Registry", "Route", "Scope", "Severity"]


class Severity(Enum):
    """Weight of a finding.

    ERROR marks a defect that should fail a build. WARNING marks a
    defect that needs triage but is not by itself an open door.
    """

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Exemption:
    """A deliberate opt-out from a check.

    Attach one to a Route that is genuinely public, or to a Scope that
    deliberately protects no HTTP route. The reason is mandatory in
    practice: an Exemption whose reason is empty or whitespace is
    itself reported as a finding by check_exemptions.
    """

    reason: str

    def has_reason(self) -> bool:
        """Return True if the reason contains non-whitespace text."""
        return bool(self.reason.strip())


@dataclass(frozen=True)
class Route:
    """One registered HTTP endpoint.

    scopes holds the permission names the route declares; any iterable
    of strings is accepted and stored as a frozenset. public, when set,
    records that the route is deliberately unauthenticated.
    """

    method: str
    path: str
    handler: str
    scopes: frozenset[str] = frozenset()
    public: Exemption | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", frozenset(self.scopes))

    @property
    def subject(self) -> str:
        """Return the route's identity as used in findings, e.g. 'GET /orders'."""
        return f"{self.method.upper()} {self.path}"


@dataclass(frozen=True)
class Scope:
    """One named permission.

    routeless, when set, records that the scope deliberately protects
    something other than an HTTP route, such as a CLI command or a
    background job.
    """

    name: str
    description: str = ""
    routeless: Exemption | None = None


@dataclass
class Registry:
    """Every route and every scope the checks run over.

    Build one directly from lists, or grow it with add_route and
    add_scope, then hand it to the check functions.
    """

    routes: list[Route] = field(default_factory=list)
    scopes: list[Scope] = field(default_factory=list)

    def add_route(self, route: Route) -> Route:
        """Add a route to the registry and return it unchanged."""
        self.routes.append(route)
        return route

    def add_scope(self, scope: Scope) -> Scope:
        """Add a scope to the registry and return it unchanged."""
        self.scopes.append(scope)
        return scope

    def scope_names(self) -> frozenset[str]:
        """Return the names of every registered scope."""
        return frozenset(s.name for s in self.scopes)

    def declared_scope_names(self) -> frozenset[str]:
        """Return every scope name declared by at least one route."""
        return frozenset(name for r in self.routes for name in r.scopes)


@dataclass(frozen=True)
class Finding:
    """One defect the checks found.

    code is a stable machine-readable identifier, severity says how bad
    it is, subject names the route or scope concerned, and message is
    the human-readable explanation.
    """

    code: str
    severity: Severity
    subject: str
    message: str
