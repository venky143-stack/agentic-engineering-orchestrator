
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentResult:
    name: str
    summary: str
    artifacts: dict[str, str]
    metadata: dict[str, Any]


class RequirementAnalyst:
    name = "requirement_analyst"

    def run(self, requirement: str) -> AgentResult:
        text = requirement.strip()
        lower = text.lower()

        capabilities = []
        for keyword, label in [
            ("short", "short URL creation and redirect"),
            ("persist", "persistent URL mappings"),
            ("analytics", "click analytics"),
            ("api", "documented HTTP API"),
            ("test", "automated tests"),
        ]:
            if keyword in lower:
                capabilities.append(label)

        questions: list[str] = []
        blocking_questions: list[str] = []

        def add_question(question: str, *, blocking: bool = True) -> None:
            questions.append(question)
            if blocking:
                blocking_questions.append(question)

        is_public = any(
            word in lower for word in ("public", "globally", "global")
        )
        is_production = any(
            word in lower for word in ("production", "production-ready")
        )
        mentions_scale = any(
            word in lower
            for word in ("scale", "scalable", "high traffic", "fast")
        )

        if mentions_scale or is_production:
            add_question(
                "What are the expected peak requests per second, latency objective, "
                "availability SLO, recovery objectives, and geographic distribution?"
            )

        if is_public or is_production or "secure" in lower:
            add_question(
                "What authentication, authorization, abuse prevention, and "
                "rate-limiting controls are required for creation and analytics endpoints?"
            )

        if "analytics" in lower:
            add_question(
                "Which analytics dimensions are required, how long should events be "
                "retained, what privacy rules apply, and how should bots be handled?"
            )

        if any(
            word in lower for word in ("short link", "short-link", "url", "link")
        ):
            add_question(
                "Are custom aliases, expiration, editing, and deactivation required?",
                blocking=False,
            )

        if not questions:
            add_question(
                "What are the acceptance criteria, security requirements, operational "
                "constraints, and measurable success criteria?"
            )

        assumptions = [
            "The local prototype uses SQLite; production database selection requires "
            "workload, availability, backup, and recovery review.",
            "No numeric performance or availability target is assumed without "
            "stakeholder confirmation.",
            "Analytics scope, bot filtering, privacy requirements, and retention "
            "remain undecided until business and privacy requirements are confirmed.",
            "Optional features such as custom aliases, expiration, and editing are "
            "not assumed to be required.",
            "No deployment or external side effects occur without explicit approval.",
        ]

        enhanced = text
        llm_used = False
        llm_error = None

        if os.getenv("AEO_USE_LLM", "false").lower() == "true":
            try:
                from openai import OpenAI

                client = OpenAI()
                response = client.responses.create(
                    model=os.getenv("AEO_LLM_MODEL", "gpt-4.1-mini"),
                    input=(
                        "Summarize this software requirement in 3-5 concise sentences. "
                        "Do not invent requirements; preserve uncertainty.\n\n"
                        + text
                    ),
                )
                candidate = response.output_text.strip()
                if candidate:
                    enhanced = candidate
                    llm_used = True
            except Exception as exc:
                enhanced = text
                llm_error = (
                    "Optional LLM unavailable; deterministic fallback used "
                    f"({type(exc).__name__})."
                )

        content = "# Requirement Analysis\n\n"
        content += "## Interpreted requirement\n"
        content += enhanced + "\n\n"

        content += "## Identified capabilities\n"
        content += "\n".join(
            f"- {item}"
            for item in (capabilities or ["General software delivery"])
        )
        content += "\n\n"

        content += "## Assumptions and safe defaults\n"
        content += "\n".join(f"- {item}" for item in assumptions)
        content += "\n\n"

        content += "## Blocking questions\n"
        if blocking_questions:
            content += "\n".join(f"- {item}" for item in blocking_questions)
        else:
            content += (
                "- No blocking questions identified by the baseline heuristic; "
                "human review is still required."
            )
        content += "\n\n"

        content += "## Other unresolved questions\n"
        non_blocking_questions = [
            item for item in questions if item not in blocking_questions
        ]
        if non_blocking_questions:
            content += "\n".join(
                f"- {item}" for item in non_blocking_questions
            )
        else:
            content += "- None identified by the baseline heuristic."
        content += "\n\n"

        content += "## Readiness assessment\n"
        if blocking_questions:
            content += (
                "- Material decisions remain unresolved. Resolve the blocking "
                "questions before production promotion. Whether implementation "
                "can safely proceed depends on the task scope and agreed defaults.\n"
            )
        else:
            content += (
                "- No blocking questions were detected by the baseline heuristic. "
                "This is not proof of requirement completeness or production "
                "readiness. Human review remains necessary.\n"
            )

        if llm_error:
            content += f"\n> {llm_error}\n"

        return AgentResult(
            self.name,
            "Requirement parsed; assumptions, questions, and readiness limits recorded.",
            {"requirement_analysis.md": content},
            {
                "capabilities": capabilities,
                "questions": questions,
                "blocking_questions": blocking_questions,
                "llm_used": llm_used,
                "llm_error": llm_error,
            },
        )


class RepositoryAnalyst:
    name = "repository_analyst"

    EXCLUDED = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "generated",
    }
    SOURCE_SUFFIXES = {".py", ".js", ".ts", ".java", ".go", ".php"}

    def run(self, repository: Path, requirement: str = "") -> AgentResult:
        if not repository.exists() or not repository.is_dir():
            raise FileNotFoundError(
                f"Repository directory does not exist: {repository}"
            )

        files = []
        for path in sorted(repository.rglob("*")):
            relative = path.relative_to(repository)
            if (
                not path.is_file()
                or any(part in self.EXCLUDED for part in relative.parts)
            ):
                continue
            files.append((relative.as_posix(), path))
            if len(files) >= 250:
                break

        inventory = [name for name, _ in files]
        source_files = []
        test_files = []
        route_evidence = []
        persistence_evidence = []
        analytics_evidence = []
        framework_evidence = []
        all_text = []
        test_texts = []

        for name, path in files:
            if path.name.startswith("test_") or (
                "tests" in Path(name).parts and path.suffix == ".py"
            ):
                test_files.append(name)

            if path.suffix.lower() not in self.SOURCE_SUFFIXES:
                continue

            source_files.append(name)
            try:
                source_text = path.read_text(
                    encoding="utf-8", errors="replace"
                )[:100_000]
            except OSError:
                continue

            if name in test_files:
                test_texts.append((name, source_text))

            # Exclude tests and orchestrator implementation from application evidence.
            parts = Path(name).parts
            is_orchestrator_code = bool(parts and parts[0] == "aeo")
            if name not in test_files and not is_orchestrator_code:
                all_text.append((name, source_text))
            else:
                continue

            for number, line in enumerate(source_text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                evidence = f"`{name}:{number}` — `{stripped[:180]}`"

                if any(
                    marker in stripped.lower()
                    for marker in (
                        "@app.get",
                        "@app.post",
                        "@router.get",
                        "@router.post",
                        "@app.route",
                        "@router.route",
                    )
                ):
                    route_evidence.append(evidence)

                lower_line = stripped.lower()
                if any(
                    marker in lower_line
                    for marker in (
                        "sqlite",
                        "sqlalchemy",
                        "create table",
                        "insert into",
                        "select ",
                        "db.execute",
                    )
                ):
                    persistence_evidence.append(evidence)

                if any(
                    marker in lower_line
                    for marker in (
                        "analytics",
                        "click_count",
                        "clicked_at",
                        "insert into clicks",
                        "clicks",
                    )
                ):
                    analytics_evidence.append(evidence)

                if any(
                    marker in lower_line
                    for marker in (
                        "from fastapi",
                        "import fastapi",
                        "from flask",
                        "import flask",
                        "django",
                    )
                ):
                    framework_evidence.append(evidence)

        combined = "\n".join(source for _, source in all_text).lower()
        req = requirement.lower()

        if "fastapi" in combined:
            framework = "FastAPI (source import evidence)"
        elif "flask" in combined:
            framework = "Flask (source import evidence)"
        elif "django" in combined:
            framework = "Django (source reference evidence)"
        elif any(
            name.endswith(("package.json", "pom.xml", "go.mod"))
            for name in inventory
        ):
            framework = "Not conclusively identified; inspect project manifests"
        else:
            framework = "Not conclusively identified"

        if "sqlite" in combined:
            persistence = "SQLite references detected"
        elif any(
            term in combined
            for term in ("sqlalchemy", "postgresql", "mysql", "create table")
        ):
            persistence = "Relational persistence references detected"
        else:
            persistence = "Persistence technology not conclusively identified"

        requests_analytics = any(
            word in req
            for word in ("analytics", "click count", "click tracking")
        )
        has_click_storage = (
            "clicks" in combined
            and any(
                term in combined
                for term in ("insert into clicks", "click_count")
            )
        )
        has_analytics_tests = any(
            "analytics" in Path(name).name.lower()
            or "analytics" in source.lower()
            for name, source in test_texts
        )

        requests_deactivation = any(
            term in req for term in ("deactivat", "410 gone", "http 410")
        )
        has_deactivation_evidence = any(
            term in combined
            for term in ("is_active", "deactivated_at", "410 gone", "status.gone")
        )

        deactivation_plan = []

        if requests_deactivation:
            if has_deactivation_evidence:
                capability_status = (
                    "Deactivation-related implementation evidence found. "
                    "Inspect the actual route and persistence behavior before "
                    "deciding whether changes are needed."
                )
            else:
                capability_status = (
                    "No conclusive deactivation implementation evidence found. "
                    "The plan below is proposed, not implemented functionality."
                )

            deactivation_plan = [
                "### Proposed affected files",
                "- `service/app.py` — add the deactivation endpoint, extend URL schema initialization, and update redirect handling.",
                "- `tests/test_service.py` — test deactivation, redirects, and analytics preservation.",
                "- `tests/test_contract.py` — verify the new endpoint and documented responses in OpenAPI.",
                "",
                "### Proposed API behavior",
                "- Add `POST /api/urls/{code}/deactivate`.",
                "- Return HTTP 204 when deactivation succeeds.",
                "- Return HTTP 404 for an unknown code.",
                "- Return HTTP 204 for repeated deactivation of an existing code (idempotent behavior).",
                "- Return HTTP 410 Gone from the redirect endpoint when a URL is deactivated.",
                "- Keep the analytics endpoint available and preserve historical click records.",
                "",
                "### Proposed persistence and implementation changes",
                "- Add an `is_active` column to the existing `urls` table, defaulting existing links to active.",
                "- Plan a backward-compatible SQLite migration; do not execute it without approval.",
                "- Check active state before redirecting and before recording a new click.",
                "- Do not delete URL records or historical click rows.",
                "- Verify how existing database files will receive the schema change.",
                "",
                "### Proposed regression tests",
                "- Active URLs retain their existing redirect behavior.",
                "- Deactivated URLs return HTTP 410 and create no new click record.",
                "- Unknown codes return HTTP 404 when deactivation is requested.",
                "- Repeated deactivation is idempotent.",
                "- Historical analytics remain available after deactivation.",
                "- OpenAPI documents the endpoint and its responses.",
                "",
                "### Risks and rollback",
                "- Migrate existing databases before code relies on the new column.",
                "- Review concurrent redirect/deactivation requests and authorization.",
                "- Preserve compatibility for active links and prepare a rollback plan.",
                "",
                "**Implementation status:** proposed only; no application code or database has been changed.",
            ]
        elif requests_analytics and has_click_storage:
            capability_status = (
                "Existing click/analytics implementation evidence found; "
                "verify behavior and edge cases before proposing new code."
            )
        elif requests_analytics:
            capability_status = (
                "No conclusive click-storage implementation evidence found; "
                "inspect redirect and persistence paths before proposing changes."
            )
        else:
            capability_status = (
                "No analytics-specific change inferred from the supplied requirement."
            )

        summary = (
            f"Read-only scan found {len(inventory)} files "
            f"(maximum 250); identified {len(source_files)} source files "
            f"and {len(test_files)} likely test files."
        )

        inventory_section = "\n".join(
            f"- `{name}`" for name in inventory[:100]
        ) or "- No files found."

        report_lines = [
            "# Brownfield Impact Analysis",
            "",
            "## Requested change",
            requirement.strip()
            or "No requirement supplied to the repository analyst.",
            "",
            "## Repository evidence",
            f"- Framework: {framework}",
            f"- Persistence: {persistence}",
            f"- Files scanned: {len(inventory)} (bounded to 250 files)",
            f"- Source files inspected: {len(source_files)}",
            f"- Likely test files: {len(test_files)}",
            "",
            "## Route evidence",
            *(
                route_evidence[:30]
                or ["- No recognized route declarations found."]
            ),
            "",
            "## Persistence evidence",
            *(
                persistence_evidence[:20]
                or ["- No recognized persistence statements found."]
            ),
            "",
            "## Analytics evidence",
            *(
                analytics_evidence[:20]
                or ["- No recognized analytics/click references found."]
            ),
            "",
            "## Likely tests",
            *(
                [f"- `{name}`" for name in test_files[:50]]
                or ["- No likely test files found."]
            ),
            "",
            "## Requirement-specific impact plan",
            *(
                deactivation_plan
                if requests_deactivation
                else ["No deactivation-specific plan was generated."]
            ),
            "",
            "## Capability assessment",
            capability_status,
            "",
            "## Proposed next steps",
            "- Confirm the relevant route, persistence operation, and existing API contract.",
            "- Add or update focused regression tests before changing implementation.",
            "- If the behavior already exists, test missing edge cases instead of duplicating it.",
            "- Review compatibility, data migration, privacy, and operational risks where applicable.",
            "- Keep any proposed patch isolated until a human reviews and approves it.",
            "",
            "## Scope and limitations",
            "- This is a bounded, heuristic source scan, not a full semantic or dependency analysis.",
            "- Source code is read as text; repository code is not executed.",
            "- No repository files are modified by this analysis.",
            "",
        ]

        analysis = "\n".join(report_lines)
        inventory_content = (
            "# Repository Analysis (read-only)\n\n"
            + summary
            + "\n\n## Sample inventory\n"
            + inventory_section
            + "\n\nThe scanner does not execute repository code or modify existing files.\n"
        )

        return AgentResult(
            self.name,
            summary,
            {
                "repository_analysis.md": inventory_content,
                "brownfield_impact_analysis.md": analysis,
            },
            {
                "file_count": len(inventory),
                "source_file_count": len(source_files),
                "test_files": test_files,
                "framework": framework,
                "persistence": persistence,
                "route_evidence_count": len(route_evidence),
                "analytics_evidence_count": len(analytics_evidence),
                "requested_analytics": requests_analytics,
                "existing_analytics_evidence": has_click_storage,
                "analytics_test_evidence": has_analytics_tests,
                "requested_deactivation": requests_deactivation,
                "existing_deactivation_evidence": has_deactivation_evidence,
            },
        )


class ArchitectureAgent:
    name = "architecture_agent"

    def run(self, requirement: str) -> AgentResult:
        content = """# Architecture Proposal

```mermaid
flowchart LR
  Client --> API[FastAPI routes]
  API --> SVC[URL service]
  SVC --> DB[(SQLite / repository boundary)]
  API --> ANA[Analytics query]
  SVC --> CODE[Secure short-code generator]
```

## Components
- **API layer:** request validation, HTTP status codes, redirect responses, and OpenAPI generation.
- **Service layer:** URL creation and redirect orchestration.
- **Persistence:** SQLite tables for URL mappings and click events, with indexes on short code and event lookup.
- **Analytics:** aggregate clicks and expose a per-code summary.
- **Orchestrator:** plans work as a dependency graph, runs independent agents concurrently, records every task transition, and blocks promotion pending human approval.

## Production considerations
- Replace SQLite with a managed relational database and use migrations.
- Add rate limiting, abuse/phishing controls, authentication/authorization, retention policy, structured telemetry, and alerting.
- Define capacity targets and load-test before selecting cache, sharding, or multi-region design.
- The generated prototype is not a claim of production scalability.
"""
        lower = requirement.lower()
        requests_deactivation = (
            "deactivat" in lower
            and ("url" in lower or "link" in lower)
        )

        if requests_deactivation:
            content += """

## Brownfield change plan: URL deactivation

### Existing behavior and evidence
- Inspect `service/app.py`, the actual URL schema, redirect handler,
  analytics queries, OpenAPI contract, and existing tests before implementation.
- Treat the existing implementation as authoritative. Do not assume that
  the proposed schema or endpoint already exists.
- Preserve existing redirect behavior for active URLs.

### Proposed API contract
- Add `POST /api/urls/{code}/deactivate`.
- Successful deactivation: return a documented success response.
- Unknown code: return HTTP 404.
- Repeated deactivation: behave idempotently and return a documented response.
- Deactivated redirect: return HTTP 410 Gone without redirecting.

Confirm the response body and repeated-request status against the existing
API conventions before finalizing the contract.

### Persistence and compatibility
- Prefer an `is_active` field on the existing URL record if source inspection
  confirms that it fits the current schema and persistence model.
- Existing URLs must remain active after migration.
- Retain URL records and historical click events; do not delete them.
- Check database initialization, existing database files, and migration
  compatibility before relying on the new field.
- Check concurrent redirect and deactivation requests.

### Required regression tests
- Active URLs retain existing redirect behavior.
- Deactivated URLs return HTTP 410 and do not record new clicks.
- Unknown codes return HTTP 404 for deactivation.
- Repeated deactivation behaves predictably.
- Historical analytics remain accessible after deactivation.
- OpenAPI documents the endpoint and its responses.

### Rollout, safety, and rollback
- Propose a minimal, backward-compatible patch and migration plan.
- Identify authorization and operational risks.
- Define rollback steps without deleting URL or click-history data.
- Do not modify application code, execute migrations, or deploy as part
  of this analysis.

**Implementation status:** proposed only; no application code or database
has been changed by this architecture analysis.
"""

        return AgentResult(
            self.name,
            (
                "Architecture, production risks, and requirement-specific "
                "change plan documented."
                if requests_deactivation
                else "Architecture and production risks documented."
            ),
            {"architecture.md": content},
            {
                "review_required": True,
                "requested_deactivation": requests_deactivation,
                "proposal_only": requests_deactivation,
            },
        )


class ApiContractAgent:
    name = "api_contract_agent"

    def run(self, requirement: str) -> AgentResult:
        import yaml
        from service.app import app

        # Keep the current contract faithful to the actual application.
        schema = app.openapi()
        contract = yaml.safe_dump(
            schema,
            sort_keys=False,
            allow_unicode=True,
        )

        lower = requirement.lower()
        requests_deactivation = any(
            term in lower
            for term in ("deactivat", "410 gone", "http 410")
        )

        artifacts = {"openapi.yaml": contract}
        metadata = {
            "format": schema["openapi"],
            "source": "FastAPI app.openapi()",
            "path_count": len(schema["paths"]),
            "proposal_only": False,
        }

        if requests_deactivation:
            proposed_changes = """# Proposed API Changes

## Status

Proposal only. These endpoint and response behaviors have not been
implemented or verified against the running application.

## Proposed endpoint: Deactivate a short URL

- Method: `POST`
- Path: `/api/urls/{code}/deactivate`
- Purpose: Deactivate an existing short URL without deleting its record
  or historical click data.

### Proposed responses

| HTTP status | Meaning |
|---|---|
| `204 No Content` | Deactivation succeeded, or the existing URL was already inactive. |
| `404 Not Found` | No URL exists for the supplied code. |

### Proposed redirect behavior

The existing `GET /{code}` endpoint should retain its current redirect
behavior for active URLs. For an inactive URL, it should return
`410 Gone` and must not record a new click.

### Analytics and persistence

- Keep the URL row and historical click records.
- Add an `is_active` state with a default of active for existing URLs.
- Plan an idempotent migration for existing SQLite databases.
- Keep historical analytics accessible after deactivation.

### Decisions required before implementation

- Confirm which users or services are authorized to deactivate URLs.
- Confirm that repeated deactivation should return `204 No Content`.
- Review migration ordering, concurrent requests, and rollback behavior.

### Approval boundary

This document describes a proposed change only. Generating this proposal
does not add an endpoint, execute a schema migration, modify application
code, or deploy anything.
"""
            artifacts["proposed_api_changes.md"] = proposed_changes
            metadata["proposal_only"] = True
            metadata["proposed_api_changes_artifact"] = (
                "proposed_api_changes.md"
            )

        return AgentResult(
            self.name,
            (
                "Current OpenAPI contract and proposed API changes generated."
                if requests_deactivation
                else "OpenAPI contract generated from the application schema."
            ),
            artifacts,
            metadata,
        )


class DocsAgent:
    name = "docs_agent"

    def run(self, requirement: str) -> AgentResult:
        content = """# URL Shortener Service: Operator Notes

## Local run

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -e '.[dev]'
uvicorn service.app:app --reload
```

## API walkthrough

1. `POST /api/urls` with `{"url":"https://example.com"}`.
2. Open the returned `short_url` to receive a 307 redirect.
3. `GET /api/urls/{code}/analytics` to inspect click counts.
4. Browse `/docs` for interactive API documentation.

## Safety and scope

The service is a local prototype. Do not expose it publicly without authentication/rate limits, abuse prevention, privacy/retention review, observability, and production database migrations. The orchestrator writes into the chosen output directory and requires an explicit approval flag to mark generated artifacts as approved; it never deploys them.
"""
        return AgentResult(
            self.name,
            "Setup and operational notes drafted.",
            {"service_README.md": content},
            {},
        )