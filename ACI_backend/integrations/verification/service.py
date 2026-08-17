from django.db import transaction
from django.utils import timezone

from ACI_backend.ACIApp.models import (
    ChangedFile,
    Evidence,
    EvidenceInvalidation,
    PullRequest,
    Requirement,
    Verification,
    VerificationEvidence,
    VerificationRun,
)


FINAL_VERIFICATION_STATUSES = {
    "verified",
    "partial",
    "unverified",
    "failed",
}


def evaluate_reverification_evidence(*, requirement, pull_request):
    """Return an explainable verification conclusion from fresh evidence.

    This baseline policy only makes a strong conclusion when the requirement
    has valid code, test, and CI evidence for the pull request. It is a
    conservative bridge to a semantic evaluator: its result is deterministic,
    auditable, and can later be replaced by an AI conclusion using the same
    completion lifecycle.
    """

    evidence = list(
        Evidence.objects.filter(
            requirement=requirement,
            pull_request=pull_request,
            status="valid",
        ).order_by("id")
    )
    evidence_types = {item.evidence_type for item in evidence}

    if "code" not in evidence_types:
        return {
            "status": "unverified",
            "summary": (
                f"No valid code evidence is available for PR "
                f"#{pull_request.number}."
            ),
            "confidence": 0.0,
            "evidence": evidence,
        }

    required_types = {"code", "test", "ci"}
    missing_types = required_types - evidence_types
    if missing_types:
        labels = {
            "test": "test",
            "ci": "CI",
        }
        missing = " and ".join(
            labels[item] for item in sorted(missing_types)
        )
        return {
            "status": "partial",
            "summary": (
                f"Fresh code evidence was collected from PR "
                f"#{pull_request.number}. Missing valid {missing} evidence."
            ),
            "confidence": 0.5,
            "evidence": evidence,
        }

    return {
        "status": "verified",
        "summary": (
            f"PR #{pull_request.number} has valid code, test, and CI "
            "evidence for this requirement."
        ),
        "confidence": 0.9,
        "evidence": evidence,
    }


def ingest_changed_file_evidence(
    requirement,
    pull_request,
):
    """
    Create Evidence records for changed files associated
    with a pull request.

    Each changed file becomes a piece of code evidence
    that can later be evaluated against a requirement.
    """

    changed_files = (
        ChangedFile.objects.filter(
            commit__repository=pull_request.repository,
            commit__pull_request=pull_request,
        )
        .select_related("commit")
    )

    evidence_records = []

    for changed_file in changed_files:
        evidence, _ = Evidence.objects.update_or_create(
            requirement=requirement,
            pull_request=pull_request,
            commit=changed_file.commit,
            changed_file=changed_file,
            evidence_type="code",
            defaults={
                "status": "valid",
                "description": (
                    f"Changed file: "
                    f"{changed_file.filename}"
                ),
                "metadata": {
                    "filename": changed_file.filename,
                    "status": changed_file.status,
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "changes": changed_file.changes,
                },
            },
        )

        evidence_records.append(evidence)

    return evidence_records


def create_verification(
    requirement,
    pull_request,
):
    """
    Create or retrieve the verification for a requirement
    and pull request.

    A requirement should have at most one active verification
    for a given pull request.
    """

    verification, _ = Verification.objects.get_or_create(
        requirement=requirement,
        pull_request=pull_request,
        defaults={
            "status": "pending",
        },
    )

    return verification


@transaction.atomic
def invalidate_evidence_for_changed_file(changed_file):
    """Invalidate prior code evidence affected by a changed file.

    A code-evidence item is tied to an exact file revision. When a later
    revision of the same repository path arrives, that item is no longer
    current. The resulting invalidation is retained for auditability and any
    verification that relied on the evidence is marked stale.

    Reprocessing the same webhook is safe: the invalidation event is unique
    per evidence item and triggering changed file.
    """

    prior_evidence = (
        Evidence.objects.filter(
            evidence_type="code",
            status="valid",
            changed_file__commit__repository=changed_file.commit.repository,
            changed_file__filename=changed_file.filename,
        )
        .exclude(changed_file=changed_file)
        .select_related("changed_file")
    )

    invalidated_evidence_ids = []
    triggering_pull_request = changed_file.commit.pull_request
    if triggering_pull_request is None:
        reason = f"A newer revision changed {changed_file.filename}."
    else:
        reason = (
            f"PR #{triggering_pull_request.number} changed "
            f"{changed_file.filename}."
        )

    for evidence in prior_evidence:
        EvidenceInvalidation.objects.get_or_create(
            evidence=evidence,
            triggering_changed_file=changed_file,
            defaults={
                "reason": reason,
            },
        )
        evidence.status = "stale"
        evidence.save(update_fields=["status", "updated_at"])
        invalidated_evidence_ids.append(evidence.id)

    if invalidated_evidence_ids:
        stale_at = timezone.now()
        affected_verifications = Verification.objects.filter(
            evidence_links__evidence_id__in=invalidated_evidence_ids,
        ).distinct()

        affected_verifications.exclude(status="stale").update(
            status="stale",
            invalidated_at=stale_at,
        )

        for verification in affected_verifications:
            queue_reverification(
                verification=verification,
                triggering_changed_file=changed_file,
                reason=reason,
            )

    return EvidenceInvalidation.objects.filter(
        triggering_changed_file=changed_file,
        evidence_id__in=invalidated_evidence_ids,
    ).select_related("evidence", "triggering_changed_file")


@transaction.atomic
def queue_reverification(*, verification, triggering_changed_file, reason):
    """Queue one active re-verification run for a stale verification.

    Further changes can add more stale evidence while a run is queued or
    running, but they do not create duplicate work. Once that run reaches a
    terminal state, a future invalidation may queue the next run.
    """

    verification = Verification.objects.select_for_update().get(
        pk=verification.pk,
    )
    active_run = VerificationRun.objects.filter(
        verification=verification,
        status__in=["queued", "running"],
    ).first()

    if active_run is not None:
        return active_run

    return VerificationRun.objects.create(
        verification=verification,
        triggering_changed_file=triggering_changed_file,
        reason=reason,
    )


@transaction.atomic
def claim_reverification_run(*, run_id):
    """Claim a queued run for a worker without processing it twice."""

    run = VerificationRun.objects.select_for_update().get(pk=run_id)

    if run.status != "queued":
        return None

    run.status = "running"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    return run


@transaction.atomic
def complete_reverification_run(
    *,
    run_id,
    status,
    summary="",
    confidence=None,
    evidence=None,
):
    """Persist a re-verification conclusion and complete its run.

    The caller supplies fresh evidence selected by a rule-based or AI
    verification engine. This lifecycle function owns the durable state
    transition; it deliberately does not decide whether code satisfies a
    requirement.
    """

    if status not in FINAL_VERIFICATION_STATUSES:
        raise ValueError(f"Invalid final verification status: {status}")

    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("Confidence must be between 0 and 1.")

    run = VerificationRun.objects.select_for_update().select_related(
        "verification",
    ).get(pk=run_id)

    if run.status != "running":
        raise ValueError("Only a running re-verification can be completed.")

    verification = run.verification
    evidence = evidence or []
    invalid_evidence = [
        item
        for item in evidence
        if item.requirement_id != verification.requirement_id
    ]
    if invalid_evidence:
        raise ValueError(
            "Re-verification evidence must belong to the same requirement."
        )

    for evidence_item in evidence:
        VerificationEvidence.objects.get_or_create(
            verification=verification,
            evidence=evidence_item,
        )

    verification.status = status
    verification.summary = summary
    verification.confidence = confidence
    if status in {"verified", "partial"}:
        verification.verified_at = timezone.now()
        verification.invalidated_at = None
    verification.save(
        update_fields=[
            "status",
            "summary",
            "confidence",
            "verified_at",
            "invalidated_at",
        ],
    )

    run.status = "completed"
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at"])
    return verification


def process_next_reverification_run():
    """Process the oldest queued run using ACI's conservative baseline.

    This is intentionally not an AI evaluator. It collects fresh code evidence
    from the triggering pull request and records a ``partial`` result, clearly
    signalling that semantic verification is still required. A future
    evaluator can replace the conclusion without changing the durable queue
    lifecycle.
    """

    queued_run = VerificationRun.objects.filter(
        status="queued",
    ).order_by("requested_at").first()
    if queued_run is None:
        return None

    run = claim_reverification_run(run_id=queued_run.id)
    if run is None:
        return None

    verification = run.verification
    pull_request = run.triggering_changed_file.commit.pull_request
    if pull_request is None:
        return complete_reverification_run(
            run_id=run.id,
            status="unverified",
            summary=(
                "Re-verification could not collect code evidence because "
                "the triggering change is not associated with a pull request."
            ),
        )

    ingest_changed_file_evidence(
        requirement=verification.requirement,
        pull_request=pull_request,
    )
    conclusion = evaluate_reverification_evidence(
        requirement=verification.requirement,
        pull_request=pull_request,
    )
    return complete_reverification_run(
        run_id=run.id,
        **conclusion,
    )
