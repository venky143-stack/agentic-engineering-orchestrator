# Requirement: Scalable URL Shortener Service

Build a scalable URL shortener service with APIs, persistence, and analytics.

## Required capabilities
- Create a short code for a submitted HTTP or HTTPS URL.
- Redirect a short code to its original URL.
- Persist mappings and click events in a database.
- Expose basic click analytics for a short code.
- Validate inputs and return useful HTTP errors for unknown codes.
- Include API documentation and automated tests.

## Constraints and assumptions for this prototype
- Use Python and FastAPI with SQLite for a locally runnable demonstration.
- Keep persistence behind a small service boundary so SQLite can later be replaced.
- Do not deploy, run arbitrary shell commands, or modify a user's existing repository automatically.
- Generated outputs require human review before promotion.
- Treat this as a prototype, not a production-ready globally distributed service.
