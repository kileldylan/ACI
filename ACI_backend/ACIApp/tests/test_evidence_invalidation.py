import pytest

from ACI_backend.ACIApp.models import (
    ChangedFile,
    Commit,
    Evidence,
    EvidenceInvalidation,
    PullRequest,
    Repository,
    Requirement,
    Verification,
    VerificationEvidence,
)
from ACI_backend.integrations.verification.service import (
    invalidate_evidence_for_changed_file,
)


def create_pull_request(repository, *, number, sha):
    return PullRequest.objects.create(
        repository=repository,
        github_id=100000 + number,
        number=number,
        title="Update authentication",
        author="kilel",
        source_branch=f"feature/auth-{number}",
        target_branch="main",
        base_sha="b" * 40,
        head_sha=sha,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )


@pytest.mark.django_db
def test_changed_file_invalidates_prior_evidence_and_verification():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
    )
    requirement = Requirement.objects.create(
        repository=repository,
        external_id="AUTH-3",
        source="jira",
        title="Users can authenticate",
    )

    original_pr = create_pull_request(
        repository,
        number=3,
        sha="a" * 40,
    )
    original_commit = Commit.objects.create(
        repository=repository,
        pull_request=original_pr,
        sha="c" * 40,
        message="Implement authentication",
        author="kilel",
        committed_at="2026-08-17T10:00:00Z",
    )
    original_file = ChangedFile.objects.create(
        commit=original_commit,
        filename="auth/service.py",
        status="added",
        additions=30,
        changes=30,
    )
    evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=original_pr,
        commit=original_commit,
        changed_file=original_file,
        evidence_type="code",
        status="valid",
        description="Authentication service implements the requirement.",
    )
    verification = Verification.objects.create(
        requirement=requirement,
        pull_request=original_pr,
        status="verified",
        summary="Authentication is verified.",
        confidence=0.95,
    )
    VerificationEvidence.objects.create(
        verification=verification,
        evidence=evidence,
    )

    later_pr = create_pull_request(
        repository,
        number=517,
        sha="d" * 40,
    )
    later_commit = Commit.objects.create(
        repository=repository,
        pull_request=later_pr,
        sha="e" * 40,
        message="Refactor authentication service",
        author="kilel",
        committed_at="2026-08-18T10:00:00Z",
    )
    changed_file = ChangedFile.objects.create(
        commit=later_commit,
        filename="auth/service.py",
        status="modified",
        additions=10,
        deletions=8,
        changes=18,
    )

    invalidations = invalidate_evidence_for_changed_file(changed_file)

    assert invalidations.count() == 1
    invalidation = invalidations.get()
    assert invalidation.evidence == evidence
    assert invalidation.triggering_changed_file == changed_file
    assert invalidation.reason == (
        "PR #517 changed auth/service.py."
    )

    evidence.refresh_from_db()
    verification.refresh_from_db()
    assert evidence.status == "stale"
    assert verification.status == "stale"
    assert verification.invalidated_at is not None

    invalidate_evidence_for_changed_file(changed_file)
    assert EvidenceInvalidation.objects.count() == 1
