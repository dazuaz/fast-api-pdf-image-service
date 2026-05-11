# Security

Thank you for helping keep this project and its users safe.

## Reporting a vulnerability

Please **do not** open a public issue for security reports.

Instead, use one of these options:

1. **GitHub Security Advisories** (preferred if the repository is on GitHub): open a [private security advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) for this repository.
2. **Maintainer contact**: if you maintain a fork or cannot use advisories, contact the repository owner through a private channel they publish in the README or org profile.

Include enough detail to reproduce the issue (affected version or commit, configuration, and steps). We will aim to acknowledge reports promptly and coordinate disclosure.

## Scope

This service processes untrusted PDFs and remote URLs. Deployments should use the documented environment variables (API keys, host and bucket allowlists, HTTPS-only sources, etc.) appropriate for your threat model.
