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
    VerificationRun,
)
from ACI_backend.integrations.verification.service import (
    claim_reverification_run,
    complete_reverification_run,
    evaluate_reverification_evidence,
    invalidate_evidence_for_changed_file,
    process_next_reverification_run,
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

    run = VerificationRun.objects.get(verification=verification)
    assert run.status == "queued"
    assert run.triggering_changed_file == changed_file
    assert run.reason == "PR #517 changed auth/service.py."

    claimed_run = claim_reverification_run(run_id=run.id)
    assert claimed_run.status == "running"
    assert claimed_run.started_at is not None

    fresh_evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=later_pr,
        commit=later_commit,
        changed_file=changed_file,
        evidence_type="code",
        status="valid",
        description="Authentication service was re-verified.",
    )
    completed_verification = complete_reverification_run(
        run_id=run.id,
        status="verified",
        summary="Authentication is verified against the latest change.",
        confidence=0.96,
        evidence=[fresh_evidence],
    )

    completed_verification.refresh_from_db()
    run.refresh_from_db()
    assert completed_verification.status == "verified"
    assert completed_verification.invalidated_at is None
    assert completed_verification.evidence_links.filter(
        evidence=fresh_evidence,
    ).exists()
    assert run.status == "completed"
    assert run.completed_at is not None

    invalidate_evidence_for_changed_file(changed_file)
    assert EvidenceInvalidation.objects.count() == 1
    assert VerificationRun.objects.count() == 1


@pytest.mark.django_db
def test_process_next_reverification_run_collects_fresh_code_evidence():
    repository = Repository.objects.create(
        github_id=789012,
        owner="kilel",
        name="aci-demo-two",
        full_name="kilel/aci-demo-two",
    )
    requirement = Requirement.objects.create(
        repository=repository,
        external_id="AUTH-4",
        source="jira",
        title="Users can authenticate",
    )
    pull_request = create_pull_request(
        repository,
        number=517,
        sha="f" * 40,
    )
    commit = Commit.objects.create(
        repository=repository,
        pull_request=pull_request,
        sha="g" * 40,
        message="Refactor authentication service",
        author="kilel",
        committed_at="2026-08-18T10:00:00Z",
    )
    changed_file = ChangedFile.objects.create(
        commit=commit,
        filename="auth/service.py",
        status="modified",
        additions=10,
        deletions=8,
        changes=18,
    )
    verification = Verification.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        status="stale",
    )
    run = VerificationRun.objects.create(
        verification=verification,
        triggering_changed_file=changed_file,
        reason="PR #517 changed auth/service.py.",
    )

    result = process_next_reverification_run()

    assert result == verification
    verification.refresh_from_db()
    run.refresh_from_db()
    assert verification.status == "partial"
    assert verification.summary == (
        "Fresh code evidence was collected from PR #517. "
        "Missing valid CI and test evidence."
    )
    assert run.status == "completed"
    assert verification.evidence_links.filter(
        evidence__changed_file=changed_file,
        evidence__status="valid",
    ).exists()
    assert process_next_reverification_run() is None


@pytest.mark.django_db
def test_evidence_policy_verifies_when_code_test_and_ci_are_valid():
    repository = Repository.objects.create(
        github_id=345678,
        owner="kilel",
        name="aci-demo-three",
        full_name="kilel/aci-demo-three",
    )
    requirement = Requirement.objects.create(
        repository=repository,
        external_id="AUTH-5",
        source="jira",
        title="Users can authenticate",
    )
    pull_request = create_pull_request(
        repository,
        number=18,
        sha="h" * 40,
    )
    for evidence_type in ["code", "test", "ci"]:
        Evidence.objects.create(
            requirement=requirement,
            pull_request=pull_request,
            evidence_type=evidence_type,
            status="valid",
            description=f"Valid {evidence_type} evidence.",
        )

    conclusion = evaluate_reverification_evidence(
        requirement=requirement,
        pull_request=pull_request,
    )

    assert conclusion["status"] == "verified"
    assert conclusion["confidence"] == 0.9
    assert conclusion["summary"] == (
        "PR #18 has valid code, test, and CI evidence for this requirement."
    )
    assert len(conclusion["evidence"]) == 3
