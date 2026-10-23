from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from .agents import (
    RequirementAnalyst,
    RepositoryAnalyst,
    ArchitectureAgent,
    ApiContractAgent,
    DocsAgent,
)
from .planner import DependencyPlanner


ROOT = Path(__file__).resolve().parents[1]
TEST_TIMEOUT_SECONDS = 120


def _is_within(path: Path, parent: Path) -> bool:
    """Return True if path is parent itself or a descendant of parent."""
    return path == parent or parent in path.parents


def _artifact_target(output: Path, name: str) -> Path:
    """Resolve an artifact path and reject destinations outside output."""
    output = output.resolve()
    target = (output / name).resolve()

    if target == output or not _is_within(target, output):
        raise ValueError(f"Unsafe artifact path: {name}")

    return target


def _validate_output_path(output: Path, repository: Path) -> None:
    """Reject output paths that could overwrite repository source files."""
    output = output.resolve()
    repository = repository.resolve()
    source_root = ROOT.resolve()

    # Never allow output to replace or contain the repository itself.
    if output == repository or _is_within(repository, output):
        raise ValueError(
            f"Unsafe output path: {output} would overwrite or contain "
            "the repository."
        )

    # The orchestrator materializes implementation and test files from ROOT.
    # Do not write into ROOT or any of its source directories.
    if _is_within(output, source_root):
        generated_root = (source_root / "generated").resolve()

        # The only permitted output location inside ROOT is generated/.
        if not _is_within(output, generated_root):
            raise ValueError(
                f"Unsafe output path: {output} must not overwrite "
                "the source tree; use the generated/ directory."
            )

    # If the analyzed repository is different from ROOT, allow output inside
    # it only beneath its generated/ directory.
    if repository != source_root and _is_within(output, repository):
        generated_root = (repository / "generated").resolve()

        if not _is_within(output, generated_root):
            raise ValueError(
                f"Unsafe output path: {output} must be outside the "
                "repository or inside its generated/ directory."
            )


def run_assessment(
    requirement_path: Path,
    output: Path,
    repository: Path | None = None,
    approve: bool = False,
) -> dict:
    repository = (repository or ROOT).resolve()
    output = output.resolve()

    # Reject unsafe destinations before creating directories or writing files.
    _validate_output_path(output, repository)

    requirement = requirement_path.read_text(encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)

    agents = {
        "requirements": lambda: RequirementAnalyst().run(requirement),
        "repository": lambda: RepositoryAnalyst().run(
            repository, requirement
        ),
        "architecture": lambda: ArchitectureAgent().run(requirement),
        "api_contract": lambda: ApiContractAgent().run(requirement),
        "docs": lambda: DocsAgent().run(requirement),
        "implementation": lambda: _copy_service_artifacts(output),
        "tests": lambda: _copy_test_artifacts(output),
        "validation": lambda: _validate_source_tree(),
    }

    planner = DependencyPlanner(max_retries=1)
    results, trace = planner.execute(agents)

    artifacts = {}

    # Materialize artifacts returned by successful tasks.
    for task_id, result in results.items():
        if hasattr(result, "artifacts"):
            for name, content in result.artifacts.items():
                target = _artifact_target(output, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                artifacts[name] = str(target.relative_to(output))

        elif task_id in {"implementation", "tests"} and isinstance(
            result, dict
        ):
            for name, source in result.items():
                target = _artifact_target(output, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                artifacts[name] = str(target.relative_to(output))

    # Validate generated artifacts and execute generated service tests.
    validation = _validate_outputs(output)

    task_summaries = [
        task.to_dict() for task in planner.tasks.values()
    ]

    unsuccessful_tasks = [
        {
            "task": task["task_id"],
            "status": task["status"],
            "error": task["error"],
        }
        for task in task_summaries
        if task["status"] != "success"
    ]

    validation["all_tasks_succeeded"] = not unsuccessful_tasks
    validation["unsuccessful_tasks"] = unsuccessful_tasks

    # All task outcomes, required artifacts, and executable tests must pass.
    validation["passed"] = (
        validation["passed"] and not unsuccessful_tasks
    )

    # A CLI flag is not authenticated human approval.
    # Keep every successful assessment pending human review.
    if unsuccessful_tasks or not validation["passed"]:
        status = "failed"
    else:
        status = "awaiting_human_review"

    report = {
        "project": "Agentic Engineering Orchestrator",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "approval_requested": approve,
        "validation": validation,
        "tasks": task_summaries,
        "trace": trace,
        "artifacts": sorted(artifacts),
        "safety": {
            "deployment_performed": False,
            "deployment_authorized": False,
            "repository_modified": False,
            "human_review_required": True,
            "approval_mechanism": "caller_supplied_flag",
            "approval_authenticated": False,
        },
    }

    # Persist the report for successful, failed, and review-pending runs.
    (output / "execution_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    (output / "execution_trace.md").write_text(
        _trace_markdown(report),
        encoding="utf-8",
    )

    return report


def _copy_service_artifacts(output: Path) -> dict[str, Path]:
    service_dir = ROOT / "service"

    return {
        str(path.relative_to(ROOT)): path
        for path in service_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def _copy_test_artifacts(output: Path) -> dict[str, Path]:
    test_dir = ROOT / "tests"

    return {
        str(path.relative_to(ROOT)): path
        for path in test_dir.rglob("*")
        if path.is_file()
        and path.name.startswith("test_service")
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def _validate_source_tree() -> dict:
    required = [
        ROOT / "service" / "app.py",
        ROOT / "tests" / "test_service.py",
        ROOT / "aeo" / "planner.py",
        ROOT / "aeo" / "agents.py",
    ]

    missing = [
        str(path.relative_to(ROOT))
        for path in required
        if not path.is_file()
    ]

    return {
        "passed": not missing,
        "required_source_files": [
            str(path.relative_to(ROOT)) for path in required
        ],
        "missing_source_files": missing,
        "note": (
            "Source-presence gate only. Generated service tests "
            "are executed by the output validation gate."
        ),
    }


def _run_generated_tests(output: Path) -> dict:
    service_app = output / "service" / "app.py"
    test_file = output / "tests" / "test_service.py"

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests",
    ]

    if not service_app.is_file() or not test_file.is_file():
        missing = []

        if not service_app.is_file():
            missing.append("service/app.py")

        if not test_file.is_file():
            missing.append("tests/test_service.py")

        return {
            "passed": False,
            "skipped": True,
            "returncode": None,
            "command": command,
            "stdout": "",
            "stderr": "",
            "missing_inputs": missing,
            "note": (
                "Cannot run generated tests because required files "
                "are missing."
            ),
        }

    try:
        result = subprocess.run(
            command,
            cwd=str(output),
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
            check=False,
        )

        return {
            "passed": result.returncode == 0,
            "skipped": False,
            "returncode": result.returncode,
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timeout_seconds": TEST_TIMEOUT_SECONDS,
        }

    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

        return {
            "passed": False,
            "skipped": False,
            "returncode": None,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "timeout_seconds": TEST_TIMEOUT_SECONDS,
            "error": (
                f"Generated tests exceeded the "
                f"{TEST_TIMEOUT_SECONDS}-second timeout."
            ),
        }

    except OSError as exc:
        return {
            "passed": False,
            "skipped": False,
            "returncode": None,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
            "error": f"Could not start generated tests: {exc}",
        }


def _validate_outputs(output: Path) -> dict:
    required = [
        "requirement_analysis.md",
        "repository_analysis.md",
        "architecture.md",
        "openapi.yaml",
        "service_README.md",
    ]

    missing = [
        name
        for name in required
        if not (output / name).is_file()
    ]

    # Run tests only when the required documentation is present.
    if missing:
        test_execution = {
            "passed": False,
            "skipped": True,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "note": (
                "Generated tests were not run because required "
                "artifacts are missing."
            ),
        }
    else:
        test_execution = _run_generated_tests(output)

    passed = not missing and test_execution["passed"]

    return {
        "passed": passed,
        "required_artifacts": required,
        "missing_artifacts": missing,
        "test_execution": test_execution,
        "note": (
            "Validation requires all required artifacts and "
            "successful execution of the generated service tests."
        ),
    }


def _trace_markdown(report: dict) -> str:
    lines = [
        "# Orchestration Execution Trace",
        "",
        f"**Status:** `{report['status']}`",
        f"**Approval requested:** `{report['approval_requested']}`",
        "",
        "## Execution summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
    ]

    tasks = report["tasks"]
    counts = {
        status: sum(
            1 for task in tasks if task["status"] == status
        )
        for status in ("success", "failed", "blocked", "pending")
    }

    lines.extend(
        [
            f"| Successful tasks | {counts['success']} |",
            f"| Failed tasks | {counts['failed']} |",
            f"| Blocked tasks | {counts['blocked']} |",
            f"| Pending tasks | {counts['pending']} |",
            "",
            "## Task details",
            "",
            "| Task | Agent | Status | Attempts | Duration (ms) | Error |",
            "|---|---|---|---:|---:|---|",
        ]
    )

    for task in tasks:
        duration = (
            task["duration_ms"]
            if task["duration_ms"] is not None
            else "-"
        )
        error = (
            (task.get("error") or "-")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

        lines.append(
            f"| {task['task_id']} | {task['agent']} | "
            f"{task['status']} | {task['attempts']} | "
            f"{duration} | {error} |"
        )

    lines.extend(["", "## Event log", ""])

    for event in report["trace"]:
        timestamp = event.get("at")

        if isinstance(timestamp, (int, float)):
            timestamp_text = datetime.fromtimestamp(
                timestamp, timezone.utc
            ).isoformat()
        elif timestamp is not None:
            timestamp_text = str(timestamp)
        else:
            timestamp_text = "time unavailable"

        line = (
            f"- `{timestamp_text}` — **{event['event']}** — "
            f"`{event['task']}`"
        )

        if event.get("attempt") is not None:
            line += f" (attempt {event['attempt']})"

        if event.get("next_attempt") is not None:
            line += f"; next attempt: {event['next_attempt']}"

        if event.get("duration_ms") is not None:
            line += f"; duration: {event['duration_ms']} ms"

        if event.get("error"):
            line += f"; error: {event['error']}"

        if event.get("reason"):
            line += f"; reason: {event['reason']}"

        lines.append(line)

    validation = report["validation"]
    test_execution = validation.get("test_execution", {})
    safety = report["safety"]

    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- Overall validation passed: `{validation['passed']}`",
            f"- All planner tasks succeeded: "
            f"`{validation.get('all_tasks_succeeded', 'not recorded')}`",
            f"- Missing required artifacts: "
            f"`{validation.get('missing_artifacts', [])}`",
            f"- Generated tests passed: "
            f"`{test_execution.get('passed', False)}`",
            f"- Generated test exit code: "
            f"`{test_execution.get('returncode')}`",
        ]
    )

    unsuccessful = validation.get("unsuccessful_tasks", [])

    if unsuccessful:
        lines.extend(
            [
                "",
                "### Unsuccessful tasks",
                "",
            ]
        )

        for task in unsuccessful:
            lines.append(
                f"- `{task['task']}` — `{task['status']}`: "
                f"{task.get('error') or 'No error details recorded'}"
            )

    lines.extend(
        [
            "",
            "## Safety and approval boundary",
            "",
            f"- Approval requested: `{report['approval_requested']}`",
            f"- Approval mechanism: `{safety['approval_mechanism']}`",
            f"- Approver authenticated: `{safety['approval_authenticated']}`",
            f"- Human review required: `{safety['human_review_required']}`",
            f"- Deployment authorized: `{safety['deployment_authorized']}`",
            f"- Deployment performed: `{safety['deployment_performed']}`",
            f"- Repository modified: `{safety['repository_modified']}`",
            "",
            "A caller-supplied flag is not authenticated human approval. "
            "Passing validation does not authorize implementation or deployment.",
        ]
    )

    if test_execution.get("stdout"):
        lines.extend(
            [
                "",
                "### Generated test output",
                "",
                "```text",
                str(test_execution["stdout"]).rstrip(),
                "```",
            ]
        )

    if test_execution.get("stderr"):
        lines.extend(
            [
                "",
                "### Generated test errors and warnings",
                "",
                "```text",
                str(test_execution["stderr"]).rstrip(),
                "```",
            ]
        )

    if test_execution.get("error"):
        lines.extend(
            [
                "",
                f"**Test execution error:** {test_execution['error']}",
            ]
        )

    lines.extend(
        [
            "",
            "No deployment or external side effects were performed.",
            "",
        ]
    )

    return "\n".join(lines)