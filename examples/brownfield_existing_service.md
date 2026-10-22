
# Brownfield scenario: safely deactivate an existing short URL

Inspect the existing URL shortener repository and plan an incremental enhancement that allows an existing short URL to be deactivated.

When a short URL is deactivated, its redirect endpoint must stop redirecting users and return HTTP 410 Gone. Existing analytics must remain available so that historical click data is not lost. Repeated deactivation requests should behave predictably.

Before implementation, inspect the actual application, database schema, API routes, OpenAPI contract, and tests. Identify the exact files and functions affected, and distinguish verified facts from assumptions.

Produce:
- A proposed patch plan identifying the affected files and required code changes.
- The proposed API contract for deactivation, including success, missing-code, and repeated-request behavior.
- Database and backward-compatibility considerations.
- Tests covering active links, deactivated links, unknown codes, repeated deactivation, and preservation of historical analytics.
- Security, operational, and rollback risks.

Do not modify the repository during analysis. Do not claim that the feature has been implemented or tested unless that work actually occurred. Ask questions if a material design decision cannot be resolved from the repository or this requirement.

## Guardrails
- Preserve existing behavior for active short URLs.
- Preserve historical click analytics when a link is deactivated.
- Prefer a minimal, backward-compatible schema change.
- No dependency upgrades, database migrations, or deployment without human approval.
- Keep repository analysis read-only and require human review before implementation or production promotion.