
from aeo.agents import ArchitectureAgent


def test_architecture_includes_brownfield_deactivation_plan():
    requirement = """
    Safely deactivate an existing short URL.
    Return HTTP 410 Gone for deactivated links.
    Preserve historical click analytics.
    Do not modify the repository during analysis.
    """

    result = ArchitectureAgent().run(requirement)
    architecture = result.artifacts["architecture.md"]

    assert "Brownfield change plan: URL deactivation" in architecture
    assert "POST /api/urls/{code}/deactivate" in architecture
    assert "HTTP 410 Gone" in architecture
    assert "Historical analytics remain accessible" in architecture
    assert "Required regression tests" in architecture
    assert "rollback" in architecture.lower()
    assert "Implementation status:** proposed only" in architecture
