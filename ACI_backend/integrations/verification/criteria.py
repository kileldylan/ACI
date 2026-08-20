"""Deterministic persistence helpers for requirement verification criteria."""

from fnmatch import fnmatch

from django.db import transaction
from django.db.models import Max

from ACI_backend.ACIApp.models import (
    CriterionVerification,
    CriterionVerificationEvidence,
    Evidence,
    RequirementCriterion,
    VerificationEvidence,
)


CRITERION_VERIFICATION_STATUSES = {
    "pending",
    "satisfied",
    "partial",
    "missing",
    "not_applicable",
    "failed",
}


DEFAULT_EVIDENCE_TYPES = {
    "behavior": {"code", "runtime", "test"},
    "implementation": {"code"},
    "test": {"test"},
    "integration": {"code", "test", "ci"},
    "data": {"code", "test"},
    "security": {"code", "test", "ci"},
    "configuration": {"code", "ci"},
}


def _expected_evidence_types(criterion):
    expectations = criterion.expectations or {}
    expected_types = expectations.get("evidence_types")
    if expected_types is None and expectations.get("evidence_type"):
        expected_types = [expectations["evidence_type"]]
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    return set(expected_types or DEFAULT_EVIDENCE_TYPES.get(
        criterion.category,
        {"code"},
    ))


def _matching_evidence(*, criterion, evidence):
    expectations = criterion.expectations or {}
    expected_types = _expected_evidence_types(criterion)
    path_patterns = expectations.get("path_patterns", [])

    matches = []
    for evidence_item in evidence:
        if evidence_item.evidence_type not in expected_types:
            continue
        if path_patterns:
            filename = (
                evidence_item.changed_file.filename
                if evidence_item.changed_file_id
                else evidence_item.metadata.get("filename", "")
            )
            if not any(fnmatch(filename, pattern) for pattern in path_patterns):
                continue
        matches.append(evidence_item)
    return matches


@transaction.atomic
def execute_criteria(*, verification, evidence=None):
    """Evaluate every active criterion against the supplied evidence."""

    if evidence is None:
        evidence = Evidence.objects.filter(
            requirement=verification.requirement,
            pull_request=verification.pull_request,
            status__in=["valid", "invalid"],
        ).select_related("changed_file")
    evidence = list(evidence)
    results = []

    for criterion in list_active_criteria(requirement=verification.requirement):
        valid_evidence = _matching_evidence(
            criterion=criterion,
            evidence=[item for item in evidence if item.status == "valid"],
        )
        invalid_evidence = _matching_evidence(
            criterion=criterion,
            evidence=[item for item in evidence if item.status == "invalid"],
        )
        if valid_evidence:
            status = "satisfied"
            summary = "Matching valid evidence was collected."
            confidence = 1.0
            supporting_evidence = valid_evidence
        elif invalid_evidence:
            status = "failed"
            summary = "Matching evidence was collected but is invalid."
            confidence = 0.0
            supporting_evidence = invalid_evidence
        else:
            status = "missing"
            summary = "No matching evidence was collected."
            confidence = 0.0
            supporting_evidence = []

        results.append(record_criterion_verification(
            verification=verification,
            criterion=criterion,
            status=status,
            summary=summary,
            confidence=confidence,
            metadata={
                "evidence_types": sorted(
                    _expected_evidence_types(criterion),
                ),
            },
            evidence=supporting_evidence,
        ))
    return results


@transaction.atomic
def create_criterion(
    *,
    requirement,
    text,
    category="behavior",
    priority=0,
    required=True,
    order=None,
    expectations=None,
):
    """Create one criterion, assigning the next display order when omitted."""

    if not text or not text.strip():
        raise ValueError("Criterion text cannot be empty.")

    if order is None:
        # Locking the parent prevents concurrent generators from choosing the
        # same next order for a requirement.
        requirement.__class__.objects.select_for_update().get(pk=requirement.pk)
        highest_order = RequirementCriterion.objects.filter(
            requirement=requirement,
        ).aggregate(max_order=Max("order"))["max_order"]
        order = 0 if highest_order is None else highest_order + 1

    return RequirementCriterion.objects.create(
        requirement=requirement,
        text=text.strip(),
        category=category,
        priority=priority,
        required=required,
        order=order,
        expectations=expectations or {},
    )


@transaction.atomic
def create_criteria(*, requirement, criteria):
    """Persist structured criteria in their supplied order."""

    created = []
    for position, definition in enumerate(criteria):
        if not isinstance(definition, dict):
            raise ValueError("Each criterion definition must be a dictionary.")
        values = dict(definition)
        values.setdefault("order", position)
        created.append(create_criterion(requirement=requirement, **values))
    return created


def list_active_criteria(*, requirement):
    return RequirementCriterion.objects.filter(
        requirement=requirement,
        is_active=True,
    ).order_by("order", "id")


@transaction.atomic
def update_criterion(*, criterion, **changes):
    """Update mutable criterion attributes without permitting reassignment."""

    allowed_fields = {
        "text", "category", "priority", "required", "order", "is_active",
        "expectations",
    }
    unknown_fields = set(changes) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Unsupported criterion fields: {sorted(unknown_fields)}")
    if "text" in changes and not changes["text"].strip():
        raise ValueError("Criterion text cannot be empty.")

    for field, value in changes.items():
        setattr(criterion, field, value.strip() if field == "text" else value)
    if changes:
        criterion.save(update_fields=[*changes, "updated_at"])
    return criterion


def deactivate_criterion(*, criterion):
    return update_criterion(criterion=criterion, is_active=False)


def generate_initial_criteria(*, requirement, criteria):
    """Persist caller-supplied deterministic criteria.

    This is deliberately a stable interface, rather than natural-language
    parsing. A future semantic generator can produce the same definitions.
    """

    return create_criteria(requirement=requirement, criteria=criteria)


@transaction.atomic
def record_criterion_verification(
    *,
    verification,
    criterion,
    status,
    summary="",
    confidence=None,
    metadata=None,
    evidence=None,
):
    """Record one immutable, evidence-backed criterion evaluation.

    Multiple rows are intentionally permitted for the same criterion and
    verification so evaluators can retain their audit trail as evidence or
    rules evolve.
    """

    if status not in CRITERION_VERIFICATION_STATUSES:
        raise ValueError(f"Invalid criterion verification status: {status}")
    if criterion.requirement_id != verification.requirement_id:
        raise ValueError("Criterion must belong to the verification requirement.")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("Confidence must be between 0 and 1.")

    evidence = evidence or []
    if any(item.requirement_id != verification.requirement_id for item in evidence):
        raise ValueError(
            "Criterion verification evidence must belong to the same requirement."
        )

    result = CriterionVerification.objects.create(
        verification=verification,
        criterion=criterion,
        status=status,
        summary=summary,
        confidence=confidence,
        metadata=metadata or {},
    )
    CriterionVerificationEvidence.objects.bulk_create([
        CriterionVerificationEvidence(
            criterion_verification=result,
            evidence=evidence_item,
        )
        for evidence_item in evidence
    ])
    for evidence_item in evidence:
        # Keep the established verification-level evidence chain intact while
        # also recording which criterion used the evidence.
        VerificationEvidence.objects.get_or_create(
            verification=verification,
            evidence=evidence_item,
        )
    return result
