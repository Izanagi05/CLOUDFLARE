# Security Notes

## Security posture

This tool is intended for a single local developer workstation. It is not a multi-user service and is not intended to be exposed as a network server.

## Controls included

- Local subprocesses are launched with argument arrays and `shell=False`.
- Process working directories must exist; port values are validated.
- Service arguments must be JSON arrays of strings, not shell command strings.
- The Cloudflare API client uses HTTPS, default TLS certificate verification, bounded request timeouts, and no redirects.
- Tunnel ingress origins are restricted to `localhost` / `127.0.0.1`.
- Public hostnames must be subdomains of the configured zone.
- Existing conflicting DNS records are not overwritten automatically.
- API and tunnel tokens are stored using `keyring`, backed by the operating system credential store on Windows.
- Tokens are not intentionally written to SQLite or application logs.
- Log files are size-rotated and common token patterns are redacted.

## Known risks / limitations

- The Named Tunnel Token is passed to the `cloudflared` process securely via the `TUNNEL_TOKEN` environment variable rather than command-line arguments. This prevents process-inspection tools (such as Process Explorer, Task Manager, or WMI) from viewing the token in process argument lists.
- Service stdout/stderr is captured. A project that prints credentials or personal data may put those values into the local log file. The redactor only recognizes common patterns; it is not a complete data-loss prevention system.
- A configured executable runs with the current Windows user's privileges. Never run an executable or project you do not trust.
- A published hostname is internet-reachable unless protected separately, for example with Cloudflare Access and application-level authentication.
- The application does not validate the business security of the Laravel/React application, CORS policy, session cookies, authentication, or authorization.
- Dependency vulnerabilities may be disclosed after this release. Keep dependencies and Cloudflared up to date.

## Recommended deployment hygiene

- Use a dedicated Cloudflare API token scoped to the relevant account and zone. Do not use a Global API Key.
- Store no secrets in service arguments, project files, Git repositories, screenshots, or logs.
- Do not expose database ports, phpMyAdmin, Redis, or administrative interfaces through a public tunnel.
- Use a separate development database with test data.
- Enable Cloudflare Access for preview hosts that should not be public.
- Review route changes before publishing them. The app only manages routes explicitly saved as service hostnames.
- Back up the app database if you have important project profiles. It contains configuration metadata, not API/Tunnel tokens.

## Reporting

Before sharing a bug report, remove domain/account identifiers and private hostnames if they are sensitive. Never attach tokens, `.env` files, or raw logs containing secrets.
