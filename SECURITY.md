# security policy

## supported versions

1.0.x is the only supported line and the only line that was ever
published. the 0.x versions were development milestones, never
released to pypi, and receive nothing. fixes land as patch releases
on the newest 1.0.x; there are no backports because there is nothing
to backport to.

## reporting a vulnerability

report privately through github: the "report a vulnerability" button
under the security tab of
https://github.com/ReyDotExe/scope-parity opens a private advisory
that only the maintainer sees. do not open a public issue for a
suspected vulnerability.

this is a single-maintainer project, so the response times are
honest rather than impressive: you get an acknowledgment within
seven days, and an assessment, with either a fix or a stated plan,
within thirty. if the report is valid, the fix ships as a patch
release and the advisory is published after it.

## the trust boundary

scope-parity imports the application it checks and therefore runs
that application's module-level code, with your permissions, the
same way a test suite does. it is a tool for code you trust. "it
executed my untrusted app" is the tool working as designed and is
not a vulnerability in scope-parity; do not point it, or any other
importing tool, at code you would not run.

what is in scope: anything that makes the tool lie about what it
checked. a registry the checks silently skip part of, a finding
suppressed without an exemption, an exit code 0 from a run that did
not actually check anything. those defeat the purpose of a parity
checker and are treated as security reports, not ordinary bugs.

the release path is part of the same surface: releases are built and
published by ci from a tag, via pypi trusted publishing, with no
long-lived credential stored in the repository.
