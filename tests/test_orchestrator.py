import json
from pathlib import Path

import aeo.orchestrator as orchestrator
from aeo.orchestrator import run_assessment


def test_orchestrator_emits_reviewable_artifacts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "bundle"

    report = run_assessment(
        root / "examples" / "url_shortener.md",
        output,
        root,
    )

    assert report["status"] == "awaiting_human_review"
    assert report["validation"]["passed"]

    expected_artifacts = [
        "requirement_analysis.md",
        "repository_analysis.md",
        "architecture.md",
        "openapi.yaml",
        "service_README.md",
        "execution_report.json",
        "execution_trace.md",
        "service/app.py",
        "tests/test_service.py",
    ]

    for name in expected_artifacts:
        assert (output / name).is_file(), name

    saved = json.loads(
        (output / "execution_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert saved["safety"]["deployment_performed"] is False
    assert saved["safety"]["deployment_authorized"] is False
    assert saved["safety"]["human_review_required"] is True
    assert saved["safety"]["approval_authenticated"] is False
    assert saved["safety"]["repository_modified"] is False
    assert all(
        task["status"] == "success"
        for task in saved["tasks"]
    )


def test_approval_is_denied_when_validation_fails(
    tmp_path,
    monkeypatch,
):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "failed-validation"

    def simulate_failed_validation(_output):
        return {
            "passed": False,
            "required_artifacts": [
                "requirement_analysis.md",
                "repository_analysis.md",
                "architecture.md",
                "openapi.yaml",
                "service_README.md",
            ],
            "missing_artifacts": [],
            "test_execution": {
                "passed": False,
                "skipped": False,
                "returncode": 1,
                "command": [
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "tests",
                ],
                "stdout": "FAILED: intentional validation failure",
                "stderr": "",
                "timeout_seconds": 120,
            },
            "note": "Intentional failure injected by regression test.",
        }

    monkeypatch.setattr(
        orchestrator,
        "_validate_outputs",
        simulate_failed_validation,
    )

    report = run_assessment(
        root / "examples" / "url_shortener.md",
        output,
        root,
        approve=True,
    )

    assert report["approval_requested"] is True
    assert report["status"] == "failed"
    assert report["validation"]["passed"] is False
    assert report["validation"]["test_execution"]["passed"] is False
    assert report["safety"]["human_review_required"] is True
    assert report["safety"]["approval_authenticated"] is False
    assert report["safety"]["deployment_authorized"] is False
    assert report["safety"]["deployment_performed"] is False

    saved = json.loads(
        (output / "execution_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert saved["status"] == "failed"
    assert saved["approval_requested"] is True
    assert saved["safety"] == report["safety"]


def test_successful_validation_without_approval_requires_review(
    tmp_path,
):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "review-required"

    report = run_assessment(
        root / "examples" / "url_shortener.md",
        output,
        root,
        approve=False,
    )

    assert report["validation"]["passed"] is True
    assert report["status"] == "awaiting_human_review"
    assert report["approval_requested"] is False

    safety = report["safety"]
    assert safety["approval_mechanism"] == "caller_supplied_flag"
    assert safety["approval_authenticated"] is False
    assert safety["human_review_required"] is True
    assert safety["deployment_authorized"] is False
    assert safety["deployment_performed"] is False
    assert safety["repository_modified"] is False

    saved = json.loads(
        (output / "execution_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert saved["status"] == "awaiting_human_review"
    assert saved["safety"] == safety


def test_approval_metadata_is_explicit_and_never_authorizes_deployment(
    tmp_path,
):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "approved-bundle"

    report = run_assessment(
        root / "examples" / "url_shortener.md",
        output,
        root,
        approve=True,
    )

    assert report["validation"]["passed"] is True

    # A caller-supplied flag is not authenticated human approval.
    assert report["status"] == "awaiting_human_review"
    assert report["approval_requested"] is True

    safety = report["safety"]
    assert safety["approval_mechanism"] == "caller_supplied_flag"
    assert safety["approval_authenticated"] is False
    assert safety["deployment_authorized"] is False
    assert safety["deployment_performed"] is False
    assert safety["repository_modified"] is False
    assert safety["human_review_required"] is True

    saved = json.loads(
        (output / "execution_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert saved["status"] == "awaiting_human_review"
    assert saved["approval_requested"] is True
    assert saved["safety"] == safety


def test_output_cannot_be_repository_root(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requirement = root / "examples" / "url_shortener.md"

    try:
        run_assessment(requirement, root, root)
    except ValueError as exc:
        assert "output" in str(exc).lower()
    else:
        raise AssertionError("Expected repository-root output to be rejected")


def test_output_cannot_be_source_subdirectory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requirement = root / "examples" / "url_shortener.md"
    output = root / "service"

    original_app = (output / "app.py").read_bytes()

    try:
        run_assessment(requirement, output, root)
    except ValueError as exc:
        assert "output" in str(exc).lower()
    else:
        raise AssertionError("Expected source-directory output to be rejected")

    assert (output / "app.py").read_bytes() == original_app


def test_output_outside_repository_is_allowed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requirement = root / "examples" / "url_shortener.md"
    output = tmp_path / "review-bundle"

    report = run_assessment(requirement, output, root)

    assert report["status"] == "awaiting_human_review"
    assert (output / "execution_report.json").is_file()

def test_output_inside_generated_directory_is_allowed():
    root = Path(__file__).resolve().parents[1]
    requirement = root / "examples" / "url_shortener.md"
    output = root / "generated" / "path-guard-test"

    report = run_assessment(requirement, output, root)

    assert report["status"] == "awaiting_human_review"
    assert (output / "execution_report.json").is_file()