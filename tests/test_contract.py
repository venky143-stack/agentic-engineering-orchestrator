import yaml

from aeo.agents import ApiContractAgent
from service.app import app


def test_generated_openapi_matches_application_schema():
    result = ApiContractAgent().run(
        "Build a URL shortener with APIs, persistence, and analytics."
    )

    generated = yaml.safe_load(result.artifacts["openapi.yaml"])
    actual = app.openapi()

    assert generated == actual
    assert "/healthz" in generated["paths"]
    assert "/api/urls" in generated["paths"]
    assert "/api/urls/{code}/analytics" in generated["paths"]
    assert "/{code}" in generated["paths"]

    redirect = generated["paths"]["/{code}"]["get"]
    assert "307" in redirect["responses"]
    assert "404" in redirect["responses"]

    assert "proposed_api_changes.md" not in result.artifacts
    assert result.metadata["proposal_only"] is False


def test_deactivation_requirement_generates_proposal_only():
    result = ApiContractAgent().run(
        """
        Add URL deactivation.
        POST /api/urls/{code}/deactivate should return 204 on success
        and 404 for unknown codes. Deactivated links should return
        HTTP 410 Gone while preserving historical analytics.
        """
    )

    generated = yaml.safe_load(result.artifacts["openapi.yaml"])
    proposal = result.artifacts["proposed_api_changes.md"]

    # The actual contract must still reflect the current application.
    assert generated == app.openapi()
    assert "/api/urls/{code}/deactivate" not in generated["paths"]

    # The requested change must be documented as a proposal, not an implementation.
    assert result.metadata["proposal_only"] is True
    assert (
        result.metadata["proposed_api_changes_artifact"]
        == "proposed_api_changes.md"
    )
    assert "Proposal only" in proposal
    assert "/api/urls/{code}/deactivate" in proposal
    assert "204 No Content" in proposal
    assert "404 Not Found" in proposal
    assert "410" in proposal
    assert "historical click records" in proposal
    assert "does not add an endpoint" in proposal
