
from aeo.agents import RequirementAnalyst


def test_ambiguous_public_campaign_marks_material_questions_blocking():
    requirement = """
    Build a short-link service for a public marketing campaign.
    It should be fast, scalable, secure, and provide analytics globally.
    """

    result = RequirementAnalyst().run(requirement)
    report = result.artifacts["requirement_analysis.md"]
    report_lower = report.lower()

    assert result.metadata["blocking_questions"]
    assert "## Blocking questions" in report
    assert "availability SLO" in report
    assert "privacy rules" in report_lower
    assert "before production promotion" in report_lower
    assert "no blocking ambiguity detected" not in report_lower


def test_simple_requirement_does_not_claim_completeness():
    result = RequirementAnalyst().run("Create a short URL API.")
    report = result.artifacts["requirement_analysis.md"]
    report_lower = report.lower()

    assert "## Readiness assessment" in report
    assert "not proof of requirement completeness" in report_lower
    assert "human review remains necessary" in report_lower
