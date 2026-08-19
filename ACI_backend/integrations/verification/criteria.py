"""Deterministic persistence helpers for requirement verification criteria."""

from django.db import transaction
from django.db.models import Max

from ACI_backend.ACIApp.models import (
    CriterionVerification,
    CriterionVerificationEvidence,
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
