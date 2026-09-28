"""FastAPI adapter: build a Registry from a live FastAPI app.

The routes come from the app object, so they cannot drift from the
application the way a hand-written mirror can. The scope registry
stays hand-written and is passed in; it is the source of truth the
app is checked against.

A route's scopes are read from its security dependency tree, the same
signals FastAPI's OpenAPI generator reads: every scope contributed by
Security(scheme, scopes=[...]), whether declared as a parameter, in
the route's dependencies, or in a router's dependencies. Two markers
cover apps that authorize some other way: @declares("scope") and
@public("reason") set an attribute on the endpoint function that the
adapter reads.

A route that carries a security scheme but declares no scope at all
cannot be classified: it is authenticated, so reporting it as
unprotected would be a false positive, but the adapter cannot name
what it requires either. from_fastapi raises UnclassifiableRouteError
for those instead of guessing. Plain Depends() dependencies are not
treated as authorization; a route whose only protection is a plain
dependency needs a marker.

This module requires the fastapi extra: pip install "scope-parity[fastapi]".
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

try:
    from fastapi import FastAPI
except ImportError as exc:
    raise ImportError(
        "the FastAPI adapter requires fastapi, which is not installed; "
        'install it with: pip install "scope-parity[fastapi]"'
    ) from exc

from fastapi.routing import APIRoute
from fastapi.security.base import SecurityBase

try:
    # fastapi 0.141+ keeps included routers nested inside app.routes;
    # this iterator flattens them the same way OpenAPI generation does,
    # with prefixed paths and router dependencies merged in.
    from fastapi.routing import iter_route_contexts as _iter_route_contexts
except ImportError:  # older fastapi flattens included routers itself
    _iter_route_contexts = None

from scope_parity.model import Exemption, Registry, Route, Scope

__all__ = ["UnclassifiableRouteError", "declares", "from_fastapi", "public"]

_MARKER_ATTR = "__scope_parity__"

_F = TypeVar("_F", bound=Callable[..., object])


class UnclassifiableRouteError(Exception):
    """The adapter found routes it cannot classify.

    Each listed route carries a security scheme but declares no scope,
    so it is neither unprotected nor accountably protected. Declare
    scopes on it with Security(scheme, scopes=[...]), or mark the
    endpoint with @declares(...) or @public(...).
    """

    def __init__(self, subjects: list[str]) -> None:
        self.subjects = subjects
        listing = ", ".join(subjects)
        super().__init__(
            f"could not classify {len(subjects)} route(s): {listing}. "
            "Each has a security scheme but declares no scope. Declare scopes "
            "with Security(scheme, scopes=[...]), or mark the endpoint with "
            "@declares(...) or @public(...) from scope_parity.fastapi."
        )


def declares(*scopes: str) -> Callable[[_F], _F]:
    """Mark an endpoint as requiring the named scopes.

    For apps whose authorization does not go through FastAPI's
    Security(); the adapter unions these with any Security scopes.
    Works above or below the route decorator.
    """
    if not scopes:
        raise ValueError("declares() needs at least one scope name")

    def mark(func: _F) -> _F:
        marker = dict(getattr(func, _MARKER_ATTR, {}))
        marker["scopes"] = frozenset(marker.get("scopes", frozenset())) | frozenset(scopes)
        setattr(func, _MARKER_ATTR, marker)
        return func

    return mark


def public(reason: str) -> Callable[[_F], _F]:
    """Mark an endpoint as deliberately public, with a reason.

    The adapter turns this into the route's public Exemption. It takes
    precedence over any scopes found on the route.
    """

    def mark(func: _F) -> _F:
        marker = dict(getattr(func, _MARKER_ATTR, {}))
        marker["public"] = Exemption(reason)
        setattr(func, _MARKER_ATTR, marker)
        return func

    return mark


def _unwrap(call: Any) -> Any:
    """Unwrap functools.partial layers around a dependency callable."""
    while isinstance(call, functools.partial):
        call = call.func
    return call


def _security_signals(dependant: Any) -> tuple[frozenset[str], bool]:
    """Walk a route's dependency tree for security schemes and scopes.

    Returns the union of every scope attached to a security scheme,
    and whether any security scheme is present at all. Scopes declared
    on an outer Security() apply to schemes nested under it, matching
    what FastAPI documents in OpenAPI. The walk reads both the current
    dependant layout (own_oauth_scopes and parent_oauth_scopes, since
    fastapi 0.141) and the older one (security_requirements per node),
    so the adapter is not tied to one internal layout.
    """
    scopes: set[str] = set()
    has_scheme = False
    stack: list[tuple[Any, frozenset[str]]] = [(dependant, frozenset())]
    seen: set[int] = set()
    while stack:
        node, inherited = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        effective = (
            inherited
            | frozenset(getattr(node, "parent_oauth_scopes", None) or ())
            | frozenset(getattr(node, "own_oauth_scopes", None) or ())
        )
        for requirement in getattr(node, "security_requirements", None) or ():
            has_scheme = True
            scopes.update(requirement.scopes or ())
            scopes.update(effective)
        call = getattr(node, "call", None)
        if call is not None and isinstance(_unwrap(call), SecurityBase):
            has_scheme = True
            scopes.update(effective)
        for sub in getattr(node, "dependencies", None) or ():
            stack.append((sub, effective))
    return frozenset(scopes), has_scheme


def _classify(
    endpoint: Callable[..., Any], dependant: Any
) -> tuple[frozenset[str], Exemption | None, bool]:
    """Return (scopes, public exemption, has_security_scheme) for a route."""
    marker: dict[str, Any] = getattr(endpoint, _MARKER_ATTR, {})
    marker_scopes = frozenset(marker.get("scopes", frozenset()))
    marker_public = marker.get("public")
    security_scopes, has_scheme = _security_signals(dependant)
    return (
        marker_scopes | security_scopes,
        marker_public if isinstance(marker_public, Exemption) else None,
        has_scheme,
    )


def _iter_api_routes(app: FastAPI) -> Iterable[tuple[str, str, set[str], Any, Any]]:
    """Yield (path, name, methods, endpoint, dependant) for every API route.

    Included routers are flattened, with their prefixes applied and
    their dependencies merged into the dependant. Non-APIRoute entries
    such as the documentation routes and mounts are skipped.
    """
    if _iter_route_contexts is not None:
        for context in _iter_route_contexts(app.routes):
            if isinstance(context.original_route, APIRoute):
                yield (
                    context.path,
                    context.name,
                    context.methods or set(),
                    context.endpoint,
                    context.dependant,
                )
    else:
        for route in app.routes:
            if isinstance(route, APIRoute):
                yield (
                    route.path,
                    route.name,
                    route.methods or set(),
                    route.endpoint,
                    route.dependant,
                )


def from_fastapi(app: FastAPI, scopes: Iterable[Scope]) -> Registry:
    """Build a Registry whose routes are the app's actual routes.

    scopes is the hand-written scope registry the app is checked
    against. One Route is produced per HTTP method of every APIRoute,
    including routes on included routers; non-APIRoute entries such as
    the documentation routes and mounts are outside the adapter and
    skipped.

    Raises UnclassifiableRouteError if any route carries a security
    scheme but declares no scope, rather than reporting it as
    unprotected or protected.
    """
    registry = Registry(scopes=list(scopes))
    unclassifiable: list[str] = []
    for path, name, methods, endpoint, dependant in _iter_api_routes(app):
        route_scopes, exemption, has_scheme = _classify(endpoint, dependant)
        for method in sorted(methods):
            if exemption is not None:
                registry.add_route(Route(method, path, name, public=exemption))
            elif route_scopes:
                registry.add_route(Route(method, path, name, scopes=route_scopes))
            elif has_scheme:
                unclassifiable.append(f"{method} {path}")
            else:
                registry.add_route(Route(method, path, name))
    if unclassifiable:
        raise UnclassifiableRouteError(unclassifiable)
    return registry
