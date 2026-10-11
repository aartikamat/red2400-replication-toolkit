# Security Policy

## Supported Versions

| Version | Supported                        |
|---------|----------------------------------|
| 2.x     | Yes — active development         |
| 1.0.0   | No (tag kept for reproducing v1-era outputs; see CHANGELOG.md) |

## Reporting a Vulnerability

If you discover a security-relevant issue in this toolkit — for
example, code execution triggered by a malformed deposit, a data
leakage path in the schema loader, or a supply-chain concern about a
dependency — please **do not open a public issue**.

Contact the maintainer privately via the address in `SUPPORT.md`.
Include:

- A description of the issue and its impact.
- Steps to reproduce, if applicable.
- A suggested fix, if you have one.

You can expect an acknowledgment within 5 business days. Coordinated
public disclosure will follow once a fix is available and released,
typically within 30 days for straightforward defects.

## Scope

This project is a scientific analysis toolkit. It does not accept
network input, run as a service, or process end-user credentials.
The security surface is limited to:

- Parsing CSV files supplied by the user via `load_deposit`.
- Optional matplotlib figure generation.

Reports about issues outside this surface (e.g., dependency-only
vulnerabilities with no impact on toolkit behavior) will be handled
via routine version pinning rather than expedited release.

## Scientific-correctness reports

Scientific-correctness reports are handled as `bug` issues, not
security issues, but are treated with the same priority.
They may be reported publicly.
