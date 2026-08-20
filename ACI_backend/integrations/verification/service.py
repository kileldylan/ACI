from django.conf import settings
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ACI_backend.ACIApp.models import (
    ChangedFile,
    DeliveryDecision,
    Evidence,
    EvidenceInvalidation,
    PullRequest,
    Requirement,
    Verification,
    VerificationEvidence,
    VerificationRun,
)
from ACI_backend.integrations.verification.criteria import execute_criteria
from ACI_backend.integrations.verification.decisions import (
    create_delivery_decision,
)
from ACI_backend.integrations.verification.execution import execute_test_run


FINAL_VERIFICATION_STATUSES = {
    "verified",
    "partial",
    "unverified",
    "failed",
}

DEFAULT_GITHUB_TEST_CONTEXTS = {
    "test",
    "tests",
    "pytest",
    "unit",
    "unit-tests",
}
DEFAULT_GITHUB_CI_CONTEXTS = {
    "build",
    "ci",
    "lint",
    "codeql",
    "security",
}


def classify_github_context(context):
    """Map a GitHub check/status context to an evidence type explicitly."""

    normalized = (context or "").strip().lower()
    test_contexts = {
        item.strip().lower()
        for item in getattr(
            settings,
            "GITHUB_TEST_EVIDENCE_CONTEXTS",
            DEFAULT_GITHUB_TEST_CONTEXTS,
        )
    }
    ci_contexts = {
        item.strip().lower()
        for item in getattr(
            settings,
            "GITHUB_CI_EVIDENCE_CONTEXTS",
            DEFAULT_GITHUB_CI_CONTEXTS,
        )
    }
    if normalized in test_contexts:
        return "test"
    if normalized in ci_contexts:
        return "ci"
    return None


def validate_evaluator_conclusion(*, requirement, evidence, conclusion):
    """Validate an evaluator result before it can affect durable state."""

    required_fields = {"status", "summary", "confidence", "evidence"}
    missing_fields = required_fields - set(conclusion)
    if missing_fields:
        raise ValueError(
            "Evaluator conclusion is missing: "
            + ", ".join(sorted(missing_fields))
        )

    if conclusion["status"] not in FINAL_VERIFICATION_STATUSES:
        raise ValueError("Evaluator returned an invalid status.")
    confidence = conclusion["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("Evaluator confidence must be numeric.")
    if not 0 <= confidence <= 1:
        raise ValueError("Evaluator confidence must be between 0 and 1.")
    if not isinstance(conclusion["summary"], str):
        raise ValueError("Evaluator summary must be a string.")
    if not isinstance(conclusion["evidence"], (list, tuple)):
        raise ValueError("Evaluator evidence must be a list.")

    supplied_evidence = {item.pk: item for item in evidence}
    for item in conclusion["evidence"]:
        if item.pk not in supplied_evidence:
            raise ValueError("Evaluator referenced evidence outside its input.")
        if item.requirement_id != requirement.pk:
            raise ValueError("Evaluator evidence belongs to another requirement.")
        if item.status == "stale":
            raise ValueError("Evaluator cannot reference stale evidence.")
        if item.status == "invalid" and conclusion["status"] != "failed":
            raise ValueError(
                "Invalid evidence may only support a failed conclusion."
            )

    return conclusion


def evaluate(requirement, evidence):
    """Evaluate supplied evidence through ACI's stable evaluator contract."""

    evidence = list(evidence)
    pull_request = next(
        (item.pull_request for item in evidence if item.pull_request_id),
        None,
    )
    if pull_request is None:
        conclusion = {
            "status": "unverified",
            "summary": "No pull request is associated with the evidence.",
            "confidence": 0.0,
            "evidence": [],
        }
        return validate_evaluator_conclusion(
            requirement=requirement,
            evidence=evidence,
            conclusion=conclusion,
        )
    conclusion = _evaluate_evidence(
        requirement=requirement,
        pull_request=pull_request,
        evidence=evidence,
    )
    return validate_evaluator_conclusion(
        requirement=requirement,
        evidence=evidence,
        conclusion=conclusion,
    )


def _evaluate_evidence(*, requirement, pull_request, evidence):
    """Apply the deterministic policy to an evidence collection.

    This baseline policy only makes a strong conclusion when the requirement
    has valid code, test, and CI evidence for the pull request. It is a
    conservative bridge to a semantic evaluator: its result is deterministic,
    auditable, and can later be replaced by an AI conclusion using the same
    completion lifecycle.
    """

    evidence = list(evidence)
    valid_evidence = [item for item in evidence if item.status == "valid"]
    failed_evidence = [
        item
        for item in evidence
        if (
            item.status == "invalid"
            and item.evidence_type in {"test", "ci"}
            and item.metadata.get("source") == "github"
            and item.metadata.get("head_sha") == pull_request.head_sha
        )
    ]
    evidence_types = {item.evidence_type for item in valid_evidence}

    if failed_evidence:
        return {
            "status": "failed",
            "summary": (
                f"A test or CI check failed for the current head of PR "
                f"#{pull_request.number}."
            ),
            "confidence": 0.0,
            "evidence": valid_evidence + failed_evidence,
        }

    if "code" not in evidence_types:
        return {
            "status": "unverified",
            "summary": (
                f"No valid code evidence is available for PR "
                f"#{pull_request.number}."
            ),
            "confidence": 0.0,
            "evidence": valid_evidence,
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
            "evidence": valid_evidence,
        }

    return {
        "status": "verified",
        "summary": (
            f"PR #{pull_request.number} has valid code, test, and CI "
            "evidence for this requirement."
        ),
        "confidence": 0.9,
        "evidence": valid_evidence,
    }


def evaluate_reverification_evidence(*, requirement, pull_request):
    """Evaluate current persisted evidence for a requirement and pull request."""

    evidence = Evidence.objects.filter(
        requirement=requirement,
        pull_request=pull_request,
        status__in=["valid", "invalid"],
    ).order_by("id")
    return _evaluate_evidence(
        requirement=requirement,
        pull_request=pull_request,
        evidence=evidence,
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
        evidence, created = Evidence.objects.get_or_create(
            requirement=requirement,
            pull_request=pull_request,
            commit=changed_file.commit,
            changed_file=changed_file,
            evidence_type="code",
            defaults={
                "status": "valid",
                "description": f"Changed file: {changed_file.filename}",
                "metadata": {
                    "filename": changed_file.filename,
                    "status": changed_file.status,
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "changes": changed_file.changes,
                },
            },
        )

        if not created and evidence.status == "valid":
            evidence.description = f"Changed file: {changed_file.filename}"
            evidence.metadata = {
                "filename": changed_file.filename,
                "status": changed_file.status,
                "additions": changed_file.additions,
                "deletions": changed_file.deletions,
                "changes": changed_file.changes,
            }
            evidence.save(update_fields=["description", "metadata", "updated_at"])

        evidence_records.append(evidence)

    return evidence_records


def ingest_github_evidence(*, pull_request, commit, event, payload):
    """Persist deterministic test or CI evidence from a GitHub event."""

    if event == "check_run":
        check_run = payload["check_run"]
        name = check_run.get("name", "")
        evidence_type = classify_github_context(name)
        if evidence_type is None:
            return []
        external_key = f"check_run:{name}"
        conclusion = check_run.get("conclusion") or check_run.get("status", "")
        evidence_status = "valid" if conclusion == "success" else "invalid"
        description = f"GitHub check {name or 'unnamed'} concluded {conclusion}."
        metadata = {
            "source": "github",
            "event": event,
            "external_key": external_key,
            "name": name,
            "status": check_run.get("status", ""),
            "conclusion": check_run.get("conclusion"),
            "url": check_run.get("html_url", ""),
            "head_sha": commit.sha,
        }
    elif event == "status":
        context = payload["context"]
        external_key = f"status:{context}"
        state = payload.get("state", "")
        evidence_status = "valid" if state == "success" else "invalid"
        evidence_type = classify_github_context(context)
        if evidence_type is None:
            return []
        description = f"GitHub status {context} is {state}."
        metadata = {
            "source": "github",
            "event": event,
            "external_key": external_key,
            "context": context,
            "state": state,
            "target_url": payload.get("target_url", ""),
            "head_sha": commit.sha,
        }
    else:
        raise ValueError(f"Unsupported GitHub evidence event: {event}")

    evidence_records = []
    requirement_ids = pull_request.requirement_links.values_list(
        "requirement", flat=True,
    )
    for requirement_id in requirement_ids:
        prior_evidence = Evidence.objects.filter(
            requirement_id=requirement_id,
            pull_request=pull_request,
            evidence_type=evidence_type,
            metadata__external_key=external_key,
            status="valid",
        ).exclude(commit=commit)
        for evidence in prior_evidence:
            _invalidate_evidence(evidence, triggering_commit=commit)

        evidence, _ = Evidence.objects.update_or_create(
            requirement_id=requirement_id,
            pull_request=pull_request,
            commit=commit,
            evidence_type=evidence_type,
            metadata__external_key=external_key,
            defaults={
                "status": evidence_status,
                "description": description,
                "metadata": metadata,
            },
        )
        evidence_records.append(evidence)

    return evidence_records


def _invalidate_evidence(evidence, *, triggering_commit):
    """Mark non-file evidence stale and queue affected verifications."""

    evidence.status = "stale"
    evidence.save(update_fields=["status", "updated_at"])
    affected_verifications = Verification.objects.filter(
        evidence_links__evidence=evidence,
    ).distinct()
    stale_at = timezone.now()
    affected_verifications.exclude(status="stale").update(
        status="stale",
        invalidated_at=stale_at,
    )
    DeliveryDecision.objects.filter(
        verification__in=affected_verifications,
        is_current=True,
    ).exclude(status="stale").update(
        status="stale",
        invalidated_at=stale_at,
    )
    triggering_file = triggering_commit.changed_files.order_by("id").first()
    if triggering_file is not None:
        for verification in affected_verifications:
            queue_reverification(
                verification=verification,
                triggering_changed_file=triggering_file,
                reason=f"A newer GitHub result arrived for {triggering_commit.sha}.",
            )


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
        DeliveryDecision.objects.filter(
            verification__in=affected_verifications,
            is_current=True,
        ).exclude(status="stale").update(
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
def recover_stuck_reverification_runs(*, timeout=timedelta(hours=1), now=None):
    """Fail runs left running after a worker stopped responding."""

    now = now or timezone.now()
    cutoff = now - timeout
    stuck_runs = list(
        VerificationRun.objects.select_for_update().filter(
            status="running",
            started_at__isnull=False,
            started_at__lt=cutoff,
        ).select_related("verification")
    )

    for run in stuck_runs:
        verification = run.verification
        summary = (
            "Re-verification worker did not complete within the allowed "
            "time window."
        )
        verification.status = "failed"
        verification.summary = summary
        verification.save(update_fields=["status", "summary"])
        DeliveryDecision.objects.filter(
            verification=verification,
            is_current=True,
        ).exclude(status="stale").update(
            status="stale",
            invalidated_at=now,
        )
        run.status = "failed"
        run.completed_at = now
        run.save(update_fields=["status", "completed_at"])

    return stuck_runs


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
    if confidence is not None:
        validate_evaluator_conclusion(
            requirement=verification.requirement,
            evidence=evidence,
            conclusion={
                "status": status,
                "summary": summary,
                "confidence": confidence,
                "evidence": evidence,
            },
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


def process_next_reverification_run(*, evaluator=None, test_runner=None):
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
    if test_runner is not None:
        execute_test_run(
            verification_run=run,
            runner=test_runner,
        )
    current_evidence = Evidence.objects.filter(
        requirement=verification.requirement,
        pull_request=pull_request,
        status__in=["valid", "invalid"],
    ).order_by("id")
    if evaluator is None:
        conclusion = evaluate(
            verification.requirement,
            current_evidence,
        )
    else:
        conclusion = evaluator.evaluate(
            verification.requirement,
            current_evidence,
        )
        validate_evaluator_conclusion(
            requirement=verification.requirement,
            evidence=current_evidence,
            conclusion=conclusion,
        )
    execute_criteria(
        verification=verification,
        evidence=current_evidence,
    )
    verification = complete_reverification_run(
        run_id=run.id,
        **conclusion,
    )
    create_delivery_decision(verification=verification)
    return verification
