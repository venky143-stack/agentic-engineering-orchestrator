# Agentic Engineering Orchestrator (AEO)
## Project Guide, Architecture, Demonstration Commands, and Technical Trade-offs

## 1. Project Overview

The Agentic Engineering Orchestrator (AEO) is a safety-first prototype that demonstrates how agentic engineering workflows can analyze requirements, inspect an existing repository, plan engineering tasks, coordinate execution, validate outputs, and prepare results for human review.

The objective is to demonstrate a controlled engineering workflow rather than simply use an LLM to generate code.

Traditional AI coding tools often focus on producing individual code changes. AEO demonstrates a broader workflow:

1. Understand a requirement.
2. Identify ambiguities and constraints.
3. Analyze the existing repository.
4. Decompose the work into dependent tasks.
5. Execute tasks using a dependency-aware scheduler.
6. Retry eligible failures within configured limits.
7. Validate generated artifacts and tests.
8. Produce an execution report and trace.
9. Require human review before implementation or deployment decisions.

**Core design principle:** Successful execution and validation do not automatically authorize production changes.

The current prototype is deterministic by default. Optional LLM functionality assists with requirement summarization, but it does not control task scheduling or grant deployment authority.

## 2. Problem Statement

Engineering tasks frequently require coordination across requirements, application code, API contracts, tests, documentation, and infrastructure.

A change that appears simple can have wider consequences.

For example, deactivating a shortened URL may affect:

- The API contract.
- Database schema and migration strategy.
- Redirect behavior.
- Historical analytics.
- Existing integration tests.
- Documentation and client expectations.
- Authorization and audit requirements.

AEO aims to make these dependencies explicit and create a reviewable record of what happened.

### Expected outcomes

- Repeatable execution with explicit task dependencies.
- Clear separation between analysis, implementation, and validation.
- Bounded retries instead of unlimited re-execution.
- Failure propagation to dependent tasks.
- Continued execution of independent tasks where possible.
- Machine-readable execution reports.
- Human review before high-impact actions.

## 3. Architecture

The prototype contains several cooperating components.

### 3.1 Requirement Analyst

**Responsibility:** Interpret the requested engineering change.

The baseline implementation uses transparent keyword-based heuristics to identify requirements and relevant constraints.

Optional LLM functionality can summarize the requirement, but execution remains controlled by deterministic workflow logic.

**Current limitation:** It is not a full requirements-engineering system. It does not guarantee that every ambiguity, security constraint, or hidden business rule will be discovered.

### 3.2 Repository Analyst

**Responsibility:** Perform a bounded, read-only inspection of an existing repository.

The analyst inventories supported source and project files, skips common generated and environment directories, and produces repository and brownfield impact reports.

For example, when analyzing a URL shortener, it can identify the existing API routes, service implementation, tests, and documentation relevant to a proposed deactivation feature.

**Current limitation:** The analysis is heuristic and text-based. It does not build a complete semantic dependency graph for arbitrary programming languages.

### 3.3 Planner and DAG Scheduler

**Responsibility:** Convert work into tasks with dependencies.

The planner represents the workflow as a directed acyclic graph (DAG).

Example:

- Requirement analysis must finish before architecture planning.
- API contract generation depends on the requirement and architecture.
- Implementation depends on the relevant design and contract.
- Tests and documentation depend on the artifacts they need.
- Final validation depends on the required outputs.

Tasks whose dependencies have completed can execute concurrently, subject to the scheduler's concurrency limit.

The current planner supports bounded retries and records task outcomes.

When a task fails after its retry limit, dependent tasks are marked blocked. Independent tasks can continue if they do not depend on the failed task.

### 3.4 Artifact Providers and Agents

**Responsibility:** Produce reviewable outputs for individual workflow tasks.

The prototype includes functionality for requirement analysis, repository analysis, architecture, API contracts, documentation, implementation, and validation.

The API contract provider generates an OpenAPI description from the existing FastAPI service. For a proposed deactivation feature, it can also generate a proposal document describing the intended contract and impact.

**Important distinction:** The current implementation provider copies a known example service. It does not autonomously create and safely apply arbitrary source-code patches to an existing production application.

### 3.5 Validation Gate

**Responsibility:** Determine whether required artifacts exist and whether the generated service tests pass.

The orchestrator checks required outputs and executes the relevant tests. Test execution has a configured 120-second timeout.

A passing validation gate means the configured checks passed. It does not prove that the system is secure, performant, resilient, or production-ready.

### 3.6 Human Review and Safety Controls

The orchestrator distinguishes workflow success from approval to make changes.

The current `--approve` flag records an approval request. It is not an authenticated approval mechanism.

A successful assessment remains in `awaiting_human_review` status until a real approval workflow exists.

The prototype does not authorize deployment, perform deployment, or modify the original repository as part of its normal assessment workflow.

A production implementation would need identity verification, authorization policies, an auditable approval record, and enforcement at the point where changes are applied.

## 4. Execution Flow

The high-level execution sequence is:

1. Read the requirement file.
2. Analyze the requirement and applicable constraints.
3. Inspect the target repository in read-only mode.
4. Build the task dependency graph.
5. Execute eligible tasks with bounded concurrency and retries.
6. Generate the planned artifacts.
7. Run the configured validation checks.
8. Record task events and outcomes.
9. Produce an execution report.
10. Return a result that requires human review if validation succeeds.

The main outcome states are:

- `awaiting_human_review`: The configured validation checks passed, but approval and deployment have not been authorized.
- `failed`: The assessment or required validation failed.

The execution trace provides evidence of the workflow's progress, failures, retries, and blocked dependencies.

## 5. Example Scenarios

### 5.1 Greenfield scenario

**Example:** Build a basic URL-shortening service.

The workflow analyzes the requirement, plans the tasks, produces service-related artifacts, generates an API contract and documentation, and runs tests.

The aim is to demonstrate a repeatable, structured workflow for a new service.

### 5.2 Brownfield scenario

**Example:** Add URL deactivation to an existing service.

The proposed change must preserve historical analytics and prevent inactive URLs from redirecting.

The analysis should identify the following work:

- Propose `POST /api/urls/{code}/deactivate`.
- Return `204` when deactivation succeeds.
- Return `404` for an unknown URL.
- Return `410 Gone` when a deactivated URL is used for redirection.
- Preserve historical click records and analytics.
- Introduce a migration for the active-state field.
- Add tests for active, inactive, unknown, and repeatedly deactivated URLs.
- Update the API contract and documentation.
- Identify authorization and audit requirements.

The current brownfield workflow produces impact analysis and a proposed API change document. It does not automatically implement this feature in the original service.

### 5.3 Ambiguous requirement scenario

**Example:** A requirement asks to make the service more reliable without specifying the expected service-level objective.

A responsible engineering workflow should identify unanswered questions such as:

- What availability target is required?
- What are the latency objectives?
- What is the expected traffic volume?
- What recovery time and data-loss objectives apply?
- What is the acceptable budget?
- Who approves changes to production?

AEO's heuristic analyst can help surface requirement concerns, but its output still needs human review.

## 6. Environment Setup

The commands below assume Windows with Git Bash and Python 3.11, as used during development.

From the project directory:

```bash
cd ~/Downloads/agentic-engineering-orchestrator/agentic-engineering-orchestrator
```

Confirm the Python version:

```bash
python --version
```

Activate the existing virtual environment:

```bash
source ../.venv/Scripts/activate
```

Verify the environment:

```bash
which python
python --version
```

Install the project in editable mode, if not already installed:

```bash
python -m pip install -e .
```

Check the installed CLI:

```bash
aeo --help
```

Alternatively, invoke the CLI as a Python module:

```bash
python -m aeo.cli --help
```

If dependencies are missing, install them according to the dependency definitions in `pyproject.toml`.

## 7. Demonstration Commands

### 7.1 Run the default URL-shortener assessment

```bash
python -m aeo.cli \
  --requirement examples/url_shortener.md \
  --output generated/demo-greenfield \
  --repo .
```

This command specifies:

- `--requirement`: the input Markdown requirement.
- `--output`: the directory for generated artifacts and reports.
- `--repo`: the repository to analyze in read-only mode.

On a successful run, the expected outcome is `awaiting_human_review`, rather than automatic deployment.

### 7.2 Run the brownfield scenario

```bash
python -m aeo.cli \
  --requirement examples/brownfield_existing_service.md \
  --output generated/demo-brownfield \
  --repo .
```

Review the generated impact analysis and proposal documents. Verify that the proposed API change is not misrepresented as an implemented feature.

### 7.3 Run the ambiguous requirement scenario

```bash
python -m aeo.cli \
  --requirement examples/ambiguous_requirements.md \
  --output generated/demo-ambiguous \
  --repo .
```

Use the resulting requirement analysis to explain how uncertainty should be surfaced before execution proceeds.

### 7.4 Request a human review

```bash
python -m aeo.cli \
  --requirement examples/url_shortener.md \
  --output generated/demo-review \
  --repo . \
  --approve
```

The `--approve` option records that review was requested. It does not authenticate an approver or authorize implementation or deployment.

A successful assessment should still require human review.

### 7.5 Run the test suite

```bash
python -m pytest -q
```

The last recorded full test run during development reported **22 passed and 1 non-fatal deprecation warning**. Rerun the tests in the current environment to verify the latest code.

To run specific test groups:

```bash
python -m pytest tests/test_planner.py -q
python -m pytest tests/test_orchestrator.py -q
python -m pytest tests/test_repository_analyst.py -q
python -m pytest tests/test_requirement_analyst.py -q
python -m pytest tests/test_contract.py -q
python -m pytest tests/test_service.py -q
```

### 7.6 Inspect the generated outputs

List generated files:

```bash
find generated/demo-greenfield -maxdepth 3 -type f -print
```

The exact file list depends on the scenario and implementation. Inspect the execution report, trace, validation output, API contract, and analysis documents that the workflow generated.

For example:

```bash
find generated/demo-brownfield -maxdepth 3 -type f -print
```

Open Markdown artifacts using your editor or inspect them from the terminal:

```bash
cat generated/demo-brownfield/brownfield_impact_analysis.md
```

Use the actual filenames produced by your run if they differ.

## 8. Running the Example Service

The prototype's example service is built with FastAPI.

Start the local development server:

```bash
uvicorn service.app:app --reload
```

Open the interactive API documentation in your browser:

```text
http://127.0.0.1:8000/docs
```

Check service health:

```bash
curl http://127.0.0.1:8000/healthz
```

Create a short URL:

```bash
curl -X POST http://127.0.0.1:8000/api/urls \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

Use the returned short code to query analytics:

```bash
curl http://127.0.0.1:8000/api/urls/YOUR_SHORT_CODE/analytics
```

Replace `YOUR_SHORT_CODE` with the code returned by the API.

These commands demonstrate the current example service. They do not mean that the proposed brownfield deactivation endpoint has been implemented.

Stop the development server with `Ctrl+C`.

## 9. Optional LLM Functionality

The baseline workflow is deterministic and does not require an OpenAI API key.

The `.env.example` file documents optional configuration:

```dotenv
AEO_USE_LLM=false
OPENAI_API_KEY=
AEO_LLM_MODEL=gpt-4.1-mini
```

If you choose to enable LLM functionality, configure the required environment variables according to the implementation and your account's API access.

Never commit a real `.env` file, API key, or other credential.

The optional LLM should be described as a requirement-summarization aid, not as an autonomous code-generation engine or an authority for production changes.

## 10. Generated Artifacts

Depending on the scenario and workflow, generated artifacts can include:

- Requirement analysis.
- Repository analysis.
- Brownfield impact analysis.
- Architecture documentation.
- OpenAPI contract.
- Proposed API changes.
- Implementation output.
- Generated tests.
- Documentation.
- Validation results.
- Execution report.
- Execution trace.

These artifacts make the workflow reviewable. They allow a reviewer to inspect what was requested, what the system analyzed, what it generated, what validation ran, and why human review remains necessary.

Generated files should be treated as evidence of a particular run, not as proof of production readiness.

## 11. Current Limitations and Trade-offs

### Requirement analysis

The baseline analyst uses keyword heuristics. Optional LLM functionality summarizes requirements but does not control execution.

### Repository understanding

Repository analysis is bounded and text-based. It does not provide complete semantic dependency analysis across arbitrary languages.

### Implementation

The implementation provider copies a known example service rather than generating and applying arbitrary code changes.

### Validation

Validation checks required artifacts and runs the configured service tests. Test execution has a 120-second timeout but is not isolated in a dedicated sandbox.

### Approval

The `--approve` flag is not authenticated human approval. A production workflow needs verified identity, authorization policy, and an auditable approval record.

### Production readiness

Passing validation does not establish security, performance, availability, disaster recovery, or deployment safety.

### Database

SQLite is suitable for a local demonstration but is not a substitute for a production database architecture designed around scale, availability, backup, and recovery requirements.

### Security and operations

Authentication, rate limiting, URL reputation checks, retention controls, production deployment, and load testing are not implemented as a complete production solution.

These limitations are intentional and documented. They distinguish implemented capabilities from future engineering work.

## 12. Production Roadmap

A realistic evolution of the prototype would include:

1. **Authenticated approvals:** Integrate identity and role-based authorization, with immutable approval records.
2. **Sandboxed execution:** Run tests and generated code in isolated environments with resource limits.
3. **Patch-based implementation:** Produce reviewable diffs instead of copying a fixed example service.
4. **Richer repository analysis:** Build language-aware dependency and impact graphs.
5. **Policy enforcement:** Enforce restrictions on filesystem access, network access, credentials, and production operations.
6. **Validation expansion:** Add security scanning, type checks, integration tests, contract tests, and performance tests.
7. **Observability:** Emit structured logs, trace identifiers, task metrics, retry metrics, and failure classifications.
8. **Controlled deployment:** Integrate with CI/CD only after policy checks and verified human approval.
9. **Reliability engineering:** Define service-level indicators, service-level objectives, recovery objectives, and rollback procedures.
10. **Persistent execution history:** Store reports and approvals with appropriate access controls and retention policies.

## 13. Publishing to GitHub

The local project has already been initialized and committed. The intended public repository is:

`https://github.com/venky143-stack/agentic-engineering-orchestrator`

Check the current branch, status, and remote:

```bash
git status
git branch --show-current
git remote -v
```

Review the latest commit:

```bash
git log -1 --oneline
```

Check for accidental tracked secrets or local artifacts:

```bash
git status --short
git ls-files
```

Verify that `.env`, database files, generated outputs, and virtual-environment files are not tracked.

If the `origin` remote is already configured, do not add it again. If it is missing, configure it:

```bash
git remote add origin https://github.com/venky143-stack/agentic-engineering-orchestrator.git
```

Push the `main` branch:

```bash
git push -u origin main
```

If authentication fails, use Git Credential Manager or another supported GitHub authentication method. Do not put a personal access token directly into the remote URL.

After the push succeeds, verify the repository in a browser and confirm that the README, license, source code, examples, and tests are visible.

## 14. How to Explain This Project in an Assessment

A concise explanation you can use:

> I built a safety-first Agentic Engineering Orchestrator to demonstrate how agentic workflows can move beyond code generation into structured engineering execution. The system analyzes requirements, performs bounded read-only repository analysis, plans work as a dependency graph, coordinates tasks with bounded retries, validates generated artifacts, and records an execution trace.
>
> I deliberately separated workflow success from authorization. A passing validation gate does not permit production deployment, and the current approval flag is explicitly not treated as authenticated approval. The prototype also documents where its heuristic analysis, fixed implementation provider, and non-sandboxed test execution fall short of production requirements.
>
> My next steps would be authenticated approval, sandboxed execution, reviewable patch generation, stronger policy enforcement, and deeper validation integrated with CI/CD.

## 15. Final Checklist

Before presenting the project:

- [ ] Run the complete test suite.
- [ ] Execute the greenfield, brownfield, and ambiguous scenarios.
- [ ] Inspect the generated execution report and trace.
- [ ] Verify that the approval flag does not authorize deployment.
- [ ] Confirm that no secrets or local databases are committed.
- [ ] Ensure the GitHub README accurately describes the current implementation.
- [ ] Explain the difference between prototype behavior and the production roadmap.
- [ ] Be ready to discuss retries, dependency blocking, parallelism, failure handling, human approval, and validation limitations.

**Final takeaway:** AEO is a review-first engineering orchestration prototype. Its strongest demonstration is the explicit coordination of tasks, bounded recovery, observable execution, validation, and safety boundaries—not a claim that it can autonomously deliver production changes.
