import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from ACI_backend.ACIApp.models import (
    ChangedFile,
    Commit,
    DeliveryDecision,
    Evidence,
    EvidenceInvalidation,
    PullRequest,
    Repository,
    Requirement,
    Verification,
    VerificationEvidence,
    VerificationRun,
)


@pytest.mark.django_db
def test_verification_api_exposes_stale_proof_and_queued_work():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
    )
    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=517,
        title="Refactor authentication",
        author="kilel",
        source_branch="feature/auth-refactor",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-18T10:00:00Z",
        updated_at="2026-08-18T10:00:00Z",
    )
    requirement = Requirement.objects.create(
        repository=repository,
        external_id="AUTH-3",
        source="jira",
        title="Users can authenticate",
    )
    commit = Commit.objects.create(
        repository=repository,
        pull_request=pull_request,
        sha="c" * 40,
        message="Refactor authentication service",
        author="kilel",
        committed_at="2026-08-18T10:00:00Z",
    )
    changed_file = ChangedFile.objects.create(
        commit=commit,
        filename="auth/service.py",
        status="modified",
    )
    evidence = Evidence.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        commit=commit,
        changed_file=changed_file,
        evidence_type="code",
        status="stale",
    )
    verification = Verification.objects.create(
        requirement=requirement,
        pull_request=pull_request,
        status="stale",
    )
    VerificationEvidence.objects.create(
        verification=verification,
        evidence=evidence,
    )
    EvidenceInvalidation.objects.create(
        evidence=evidence,
        triggering_changed_file=changed_file,
        reason="A newer revision changed auth/service.py.",
    )
    run = VerificationRun.objects.create(
        verification=verification,
        triggering_changed_file=changed_file,
        reason="PR #517 changed auth/service.py.",
    )
    decision = DeliveryDecision.objects.create(
        verification=verification,
        status="stale",
        summary="The verification is stale.",
        rationale={"stale_evidence_ids": [evidence.id]},
    )

    client = APIClient()
    verification_response = client.get(
        reverse("verification-list"),
        {"repository": repository.id, "status": "stale"},
    )
    evidence_response = client.get(
        reverse("evidence-list"),
        {"repository": repository.id, "status": "stale"},
    )
    run_response = client.get(
        reverse("verification-run-list"),
        {"repository": repository.id, "status": "queued"},
    )

    assert verification_response.status_code == 200
    assert verification_response.json()[0]["id"] == verification.id
    assert verification_response.json()[0]["evidence_ids"] == [evidence.id]
    assert verification_response.json()[0]["evidence"][0]["commit_sha"] == (
        commit.sha
    )
    assert verification_response.json()[0]["decision_history"][0]["id"] == (
        decision.id
    )

    assert evidence_response.status_code == 200
    assert evidence_response.json()[0]["id"] == evidence.id
    assert evidence_response.json()[0]["invalidation_history"][0]["reason"] == (
        "A newer revision changed auth/service.py."
    )

    assert run_response.status_code == 200
    assert run_response.json()[0]["id"] == run.id
    assert run_response.json()[0]["verification"] == verification.id

    decision_response = client.get(
        reverse("delivery-decision-list"),
        {"repository": repository.id},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()[0]["id"] == decision.id
    assert decision_response.json()[0]["verification_status"] == "stale"
    assert decision_response.json()[0]["evidence_ids"] == [evidence.id]
    assert decision_response.json()[0]["decision_history"][0]["id"] == decision.id
