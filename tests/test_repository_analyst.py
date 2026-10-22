
from pathlib import Path

from aeo.agents import RepositoryAnalyst


def test_brownfield_analysis_detects_existing_analytics(tmp_path):
    (tmp_path / "service").mkdir()
    (tmp_path / "tests").mkdir()

    (tmp_path / "service" / "app.py").write_text(
        "from fastapi import FastAPI\n"
        "import sqlite3\n"
        "app = FastAPI()\n"
        "@app.get('/{code}')\n"
        "def redirect(code):\n"
        "    conn.execute('INSERT INTO clicks(code) VALUES (?)', (code,))\n"
        "    return {'click_count': 1}\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_service.py").write_text(
        "def test_analytics_click_count():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = RepositoryAnalyst().run(
        tmp_path,
        "Add click analytics to the URL redirect endpoint.",
    )

    report = result.artifacts["brownfield_impact_analysis.md"]

    assert "FastAPI" in report
    assert "SQLite" in report
    assert "service/app.py" in report
    assert "tests/test_service.py" in report
    assert "Existing click/analytics implementation evidence found" in report
    assert result.metadata["existing_analytics_evidence"] is True
    assert result.metadata["analytics_test_evidence"] is True


def test_brownfield_analysis_does_not_modify_repository(tmp_path):
    app_file = tmp_path / "app.py"
    original = "def healthz():\n    return {'status': 'ok'}\n"
    app_file.write_text(original, encoding="utf-8")

    RepositoryAnalyst().run(
        tmp_path,
        "Add click analytics to the redirect endpoint.",
    )

    assert app_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / "brownfield_impact_analysis.md").exists()


def test_missing_repository_is_rejected(tmp_path):
    missing = tmp_path / "does-not-exist"

    try:
        RepositoryAnalyst().run(missing, "Add analytics.")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected missing repository to be rejected")


def test_brownfield_analysis_proposes_deactivation_plan_without_implementing_it(
    tmp_path,
):
    service_dir = tmp_path / "service"
    tests_dir = tmp_path / "tests"
    service_dir.mkdir()
    tests_dir.mkdir()

    app_file = service_dir / "app.py"
    original = (
        "from fastapi import FastAPI\n"
        "import sqlite3\n"
        "app = FastAPI()\n"
        "@app.get('/{code}')\n"
        "def redirect(code):\n"
        "    return {'url': code}\n"
    )
    app_file.write_text(original, encoding="utf-8")

    (tests_dir / "test_service.py").write_text(
        "def test_redirect():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    (tests_dir / "test_contract.py").write_text(
        "def test_openapi_contract():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    requirement = (
        "Add URL deactivation. Deactivated links must return HTTP 410 Gone, "
        "repeated deactivation must be predictable, and historical analytics "
        "must remain available."
    )

    result = RepositoryAnalyst().run(tmp_path, requirement)
    report = result.artifacts["brownfield_impact_analysis.md"]

    assert result.metadata["requested_deactivation"] is True
    assert result.metadata["existing_deactivation_evidence"] is False

    assert "Requirement-specific impact plan" in report
    assert "service/app.py" in report
    assert "tests/test_service.py" in report
    assert "tests/test_contract.py" in report
    assert "POST /api/urls/{code}/deactivate" in report
    assert "HTTP 410" in report
    assert "Historical analytics remain available" in report
    assert "Risks and rollback" in report
    assert "Implementation status:** proposed only" in report

    # The analyst must remain read-only.
    assert app_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / "brownfield_impact_analysis.md").exists()

