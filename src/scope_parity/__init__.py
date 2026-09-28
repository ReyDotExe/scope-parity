"""scope-parity: parity checks between a route registry and a scope registry.

The library takes a Registry of Route and Scope objects and returns
Finding objects describing the mismatches. It never prints; rendering
is left to callers.
"""

from scope_parity.model import Exemption, Finding, Registry, Route, Scope, Severity

__all__ = ["Exemption", "Finding", "Registry", "Route", "Scope", "Severity"]
