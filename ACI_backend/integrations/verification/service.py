from django.db import transaction
from django.utils import timezone

from ACI_backend.ACIApp.models import (
    ChangedFile,
    Evidence,
    EvidenceInvalidation,
    PullRequest,
    Requirement,
    Verification,
)


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
        Verification.objects.filter(
            evidence_links__evidence_id__in=invalidated_evidence_ids,
        ).exclude(status="stale").update(
            status="stale",
            invalidated_at=stale_at,
        )

    return EvidenceInvalidation.objects.filter(
        triggering_changed_file=changed_file,
        evidence_id__in=invalidated_evidence_ids,
    ).select_related("evidence", "triggering_changed_file")
