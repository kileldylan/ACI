import pytest

from ACI_backend.ACIApp.models import (
    Evidence,
    PullRequest,
    Repository,
    Requirement,
    VerificationEvidence,
)
from ACI_backend.ACIApp.services.verification import (
    create_verification,
)


@pytest.mark.django_db
def test_create_verification_creates_verification():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Implement authentication",
        author="kilel",
        source_branch="feature/auth",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    requirement = Requirement.objects.create(
        repository=repository,
        external_id="JIRA-104",
        source="jira",
        title="Authentication",
        description=(
            "Users must be able to authenticate."
        ),
    )

    evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        evidence_type="code",
        status="valid",
        description="Authentication logic exists.",
    )

    verification = create_verification(
        requirement=requirement,
        pull_request=pull_request,
        status="verified",
        summary="Authentication is implemented.",
        confidence=0.95,
        evidence=[evidence],
    )

    assert verification.pk is not None

    assert verification.requirement == requirement
    assert verification.pull_request == pull_request

    assert verification.status == "verified"
    assert verification.summary == (
        "Authentication is implemented."
    )

    assert verification.confidence == 0.95

    assert verification.evidence_links.count() == 1

    link = verification.evidence_links.first()

    assert link.evidence == evidence

@pytest.mark.django_db
def test_create_verification_supports_multiple_evidence_items():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Implement password reset",
        author="kilel",
        source_branch="feature/password-reset",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    requirement = Requirement.objects.create(
        repository=repository,
        external_id="JIRA-200",
        source="jira",
        title="Password reset",
        description=(
            "Users can reset their password "
            "and receive an email."
        ),
    )

    code_evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        evidence_type="code",
        status="valid",
        description="Password reset endpoint exists.",
    )

    test_evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        evidence_type="test",
        status="valid",
        description="Password reset is covered by tests.",
    )

    verification = create_verification(
        requirement=requirement,
        pull_request=pull_request,
        status="verified",
        summary="Password reset is implemented and tested.",
        confidence=0.92,
        evidence=[
            code_evidence,
            test_evidence,
        ],
    )

    assert verification.evidence_links.count() == 2

    evidence_ids = set(
        verification.evidence_links.values_list(
            "evidence_id",
            flat=True,
        )
    )

    assert evidence_ids == {
        code_evidence.id,
        test_evidence.id,
    }

@pytest.mark.django_db
def test_create_verification_rejects_invalid_status():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Test PR",
        author="kilel",
        source_branch="feature/test",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    requirement = Requirement.objects.create(
        repository=repository,
        external_id="JIRA-300",
        source="jira",
        title="Test requirement",
    )

    with pytest.raises(ValueError):
        create_verification(
            requirement=requirement,
            pull_request=pull_request,
            status="definitely_not_valid",
        )

@pytest.mark.django_db
def test_create_verification_rejects_invalid_confidence():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Test PR",
        author="kilel",
        source_branch="feature/test",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    requirement = Requirement.objects.create(
        repository=repository,
        external_id="JIRA-301",
        source="jira",
        title="Test requirement",
    )

    with pytest.raises(ValueError):
        create_verification(
            requirement=requirement,
            pull_request=pull_request,
            status="verified",
            confidence=1.5,
        )