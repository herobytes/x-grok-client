# Security

## Credentials

An X session cookie is a login credential. Enter it only through the local `init`
prompt or a trusted pipe into `init --cookie-stdin`. Do not put it in shell
arguments, issues, pull requests, screenshots, or chat messages.

The credentials file is plaintext. New files use owner-only permissions on POSIX
systems, but this is not encryption and does not protect against software running
as the same user. Keep credentials out of Git, shared folders, and public backups.
Proxy URLs can also contain passwords and require the same care.

If a cookie is exposed, revoke the affected session in X, sign in again, and run
`init --replace-cookie`. Cookie refresh does not guarantee that previous cookie
values have been invalidated.

## Reporting a vulnerability

Do not disclose credentials, raw authenticated responses, or exploitable details
in public issues. If the GitHub repository offers **Security → Report a
vulnerability**, use that private reporting channel. If it is unavailable and no
private maintainer contact is published, open an issue asking for a private
contact channel without including vulnerability details.

Include a description, affected revision, impact, and a minimal reproduction using
synthetic credentials. Do not use another person's account to demonstrate an
issue. No response-time guarantee or bug bounty is offered.

## Maintenance scope

Security fixes target the current `main` branch. Older snapshots have no separate
support policy. Runtime dependency updates affect XClientTransaction only, and
only in the dedicated environments described in
[dependency maintenance](references/dependency-maintenance.md).
