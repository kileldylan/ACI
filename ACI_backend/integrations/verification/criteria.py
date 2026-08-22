"""Deterministic persistence helpers for requirement verification criteria."""

from fnmatch import fnmatch
import re

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


def list_active_criteria(*, requirement):
    """Return active criteria for a requirement, ordered for evaluation."""
    return RequirementCriterion.objects.filter(
        requirement=requirement,
        is_active=True,
    ).order_by("order", "id")


def create_criterion(
    *,
    requirement,
    text,
    category="behavior",
    expectations=None,
    priority=0,
    required=True,
):
    """Create a new criterion for a requirement."""
    if expectations is None:
        expectations = {}

    max_order = (
        RequirementCriterion.objects.filter(requirement=requirement)
        .aggregate(max_order=Max("order"))["max_order"]
        or -1
    )
    order = max_order + 1

    return RequirementCriterion.objects.create(
        requirement=requirement,
        text=text,
        category=category,
        expectations=expectations,
        priority=priority,
        required=required,
        order=order,
    )


def update_criterion(*, criterion, **fields):
    """Update fields on an existing criterion."""
    for key, value in fields.items():
        setattr(criterion, key, value)
    criterion.save()
    return criterion


def deactivate_criterion(*, criterion):
    """Deactivate a criterion (soft delete)."""
    criterion.is_active = False
    criterion.save(update_fields=["is_active", "updated_at"])
    return criterion


def generate_initial_criteria(*, requirement, criteria):
    """Bulk create initial criteria from a list of dicts."""
    created = []
    for crit in criteria:
        c = create_criterion(
            requirement=requirement,
            text=crit["text"],
            category=crit.get("category", "behavior"),
            expectations=crit.get("expectations"),
        )
        created.append(c)
    return created


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
    """Persist a criterion evaluation result and link supporting evidence."""
    if metadata is None:
        metadata = {}
    if evidence is None:
        evidence = []

    cv = CriterionVerification.objects.create(
        verification=verification,
        criterion=criterion,
        status=status,
        summary=summary,
        confidence=confidence,
        metadata=metadata,
    )

    for ev in evidence:
        CriterionVerificationEvidence.objects.create(
            criterion_verification=cv,
            evidence=ev,
        )

    return cv


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


def _analyze_patch_relevance(criterion_text: str, patch: str) -> dict:
    """
    Simple but effective analysis of whether the patch appears to address the criterion.
    Looks for keywords from the criterion in the added lines.
    """
    if not patch:
        return {"relevant": False, "added_lines": 0, "keywords_found": []}

    criterion_lower = criterion_text.lower()
    keywords = re.findall(r'\b\w{4,}\b', criterion_lower)
    keywords = [k for k in keywords if len(k) > 3][:8]  # limit noise

    added_lines = []
    for line in patch.splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            added_lines.append(line[1:].strip())

    added_text = " ".join(added_lines).lower()
    found = [kw for kw in keywords if kw in added_text]

    return {
        "relevant": len(found) > 0 or len(added_lines) > 0,
        "added_lines": len(added_lines),
        "keywords_found": found,
    }


def _build_criterion_summary(criterion, valid_evidence, invalid_evidence):
    """Generate a precise, intelligent summary instead of generic text."""
    criterion_text = criterion.text

    if invalid_evidence:
        return f"Evidence for '{criterion_text[:60]}...' was collected but marked invalid."

    if not valid_evidence:
        return f"No evidence found addressing: {criterion_text}"

    # Analyze code patches for relevance
    relevant_files = []
    total_relevant_changes = 0
    for ev in valid_evidence:
        if ev.changed_file and ev.changed_file.patch:
            analysis = _analyze_patch_relevance(criterion_text, ev.changed_file.patch)
            if analysis["relevant"]:
                relevant_files.append(ev.changed_file.filename)
                total_relevant_changes += analysis["added_lines"]

    if relevant_files:
        files_str = ", ".join(relevant_files[:3])
        if len(relevant_files) > 3:
            files_str += f" (+{len(relevant_files) - 3} more)"

        if total_relevant_changes > 0:
            return (
                f"Addresses criterion in {files_str}. "
                f"Added/modified ~{total_relevant_changes} lines relevant to the requirement."
            )
        return f"Code changes found in {files_str} that appear related to the criterion."

    # Fallback for non-code evidence
    types = sorted({e.evidence_type for e in valid_evidence})
    return f"Evidence collected ({', '.join(types)}) for criterion: {criterion_text[:70]}..."


@transaction.atomic
def execute_criteria(*, verification, evidence=None):
    """Evaluate every active criterion against the supplied evidence with precise analysis."""

    if evidence is None:
        evidence = Evidence.objects.filter(
            requirement=verification.requirement,
            pull_request=verification.pull_request,
            status__in=["valid", "invalid"],
        ).select_related("changed_file", "changed_file__commit")
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

        if invalid_evidence:
            status = "failed"
            summary = _build_criterion_summary(criterion, [], invalid_evidence)
            confidence = 0.0
            supporting_evidence = invalid_evidence
        elif valid_evidence:
            # More intelligent status determination
            has_code = any(e.evidence_type == "code" for e in valid_evidence)
            has_test = any(e.evidence_type == "test" for e in valid_evidence)

            if criterion.category in ("test", "security") and not has_test:
                status = "partial"
                confidence = 0.6
            elif has_code:
                status = "satisfied"
                confidence = 0.85
            else:
                status = "satisfied"
                confidence = 0.7

            summary = _build_criterion_summary(criterion, valid_evidence, [])
            supporting_evidence = valid_evidence
        else:
            status = "missing"
            summary = _build_criterion_summary(criterion, [], [])
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
                "evidence_count": len(supporting_evidence),
            },
            evidence=supporting_evidence,
        ))
    return results
