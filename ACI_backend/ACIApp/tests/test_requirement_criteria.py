import pytest

from ACI_backend.ACIApp.models import (
    Evidence,
    PullRequest,
    Repository,
    Requirement,
    Verification,
)
from ACI_backend.integrations.verification.criteria import (
    create_criterion,
    deactivate_criterion,
    generate_initial_criteria,
    list_active_criteria,
    record_criterion_verification,
    update_criterion,
)


@pytest.fixture
def requirement():
    repository = Repository.objects.create(
        github_id=99001,
        owner="aci",
        name="criteria",
        full_name="aci/criteria",
    )
    return Requirement.objects.create(
        repository=repository,
        external_id="ACI-1",
        source="manual",
        title="Reset passwords",
    )


@pytest.mark.django_db
def test_criteria_service_persists_structured_expectations(requirement):
    criteria = generate_initial_criteria(requirement=requirement, criteria=[
        {"text": "A reset flow exists.", "category": "behavior"},
        {
            "text": "A reset email is sent.",
            "category": "integration",
            "expectations": {"path_patterns": ["**/email*.py"]},
        },
    ])

    assert [criterion.order for criterion in criteria] == [0, 1]
    assert criteria[1].expectations["path_patterns"] == ["**/email*.py"]
    assert list(list_active_criteria(requirement=requirement)) == criteria

    update_criterion(criterion=criteria[0], priority=10)
    deactivate_criterion(criterion=criteria[1])
    assert criteria[0].priority == 10
    assert list(list_active_criteria(requirement=requirement)) == [criteria[0]]


@pytest.mark.django_db
def test_criterion_results_retain_evidence_traceability(requirement):
    criterion = create_criterion(requirement=requirement, text="Reset view exists.")
    pull_request = PullRequest.objects.create(
        repository=requirement.repository,
        github_id=99002,
        number=1,
        title="Reset passwords",
        author="aci",
        source_branch="feature/reset",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        created_at="2026-08-19T07:00:00Z",
        updated_at="2026-08-19T07:00:00Z",
    )
    verification = Verification.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        status="partial",
    )
    evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        evidence_type="code",
    )
    result = record_criterion_verification(
        verification=verification,
        criterion=criterion,
        status="satisfied",
        evidence=[evidence],
    )

    assert result in verification.criterion_results.all()
    assert result.evidence_links.get().evidence == evidence
    assert evidence.criterion_verification_links.get().criterion_verification == result
    assert verification.evidence_links.get().evidence == evidence
