from django.db import models

class Repository(models.Model):
    """A GitHub repository connected to ACI."""

    github_id = models.BigIntegerField(unique=True)

    owner = models.CharField(max_length=255)
    name = models.CharField(max_length=255)

    full_name = models.CharField(
        max_length=512,
        unique=True,
    )

    default_branch = models.CharField(
        max_length=255,
        default="main",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name


class PullRequest(models.Model):
    """A GitHub pull request that ACI needs to analyze."""

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="pull_requests",
    )

    github_id = models.BigIntegerField()

    number = models.PositiveIntegerField()

    title = models.CharField(max_length=500)

    author = models.CharField(max_length=255)

    source_branch = models.CharField(max_length=255)
    target_branch = models.CharField(max_length=255)

    base_sha = models.CharField(max_length=40)
    head_sha = models.CharField(max_length=40)

    state = models.CharField(
        max_length=20,
        default="open",
    )

    is_merged = models.BooleanField(default=False)

    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    received_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "number"],
                name="unique_repository_pull_request",
            ),
        ]

        indexes = [
            models.Index(
                fields=["repository", "state"],
            ),
            models.Index(
                fields=["head_sha"],
            ),
        ]

    def __str__(self):
        return f"{self.repository.full_name}#{self.number}"

class Commit(models.Model):
    """A Git commit associated with a pull request."""

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="commits",
    )

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="commits",
        null=True,
        blank=True,
    )

    sha = models.CharField(
        max_length=40,
        unique=True,
    )

    message = models.TextField()

    author = models.CharField(max_length=255)

    committed_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.sha

class ChangedFile(models.Model):
    commit = models.ForeignKey(
        Commit,
        on_delete=models.CASCADE,
        related_name="changed_files",
    )

    filename = models.CharField(max_length=1024)

    status = models.CharField(max_length=50)

    additions = models.PositiveIntegerField(default=0)

    deletions = models.PositiveIntegerField(default=0)

    changes = models.PositiveIntegerField(default=0)

    patch = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

class Requirement(models.Model):
    SOURCE_CHOICES = [
        ("jira", "Jira"),
        ("linear", "Linear"),
        ("github", "GitHub"),
        ("manual", "Manual"),
    ]

    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="requirements",
    )

    external_id = models.CharField(max_length=255)
    source = models.CharField(
        max_length=50,
        choices=SOURCE_CHOICES,
        default="jira",
    )

    title = models.CharField(max_length=500)

    description = models.TextField(blank=True)

    url = models.URLField(blank=True)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="open",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "source", "external_id"],
                name="unique_requirement_source_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.source}:{self.external_id} - {self.title}"

class RequirementPullRequest(models.Model):
    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="pull_request_links",
    )

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="requirement_links",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requirement", "pull_request"],
                name="unique_requirement_pull_request",
            ),
        ]

    def __str__(self):
        return (
            f"{self.requirement} -> "
            f"{self.pull_request}"
        )

class Evidence(models.Model):
    TYPE_CHOICES = [
        ("code", "Code"),
        ("test", "Test"),
        ("ci", "CI"),
        ("runtime", "Runtime"),
    ]

    STATUS_CHOICES = [
        ("valid", "Valid"),
        ("stale", "Stale"),
        ("invalid", "Invalid"),
    ]

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="evidence",
    )

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="evidence",
        null=True,
        blank=True,
    )

    commit = models.ForeignKey(
        Commit,
        on_delete=models.CASCADE,
        related_name="evidence",
        null=True,
        blank=True,
    )

    changed_file = models.ForeignKey(
        ChangedFile,
        on_delete=models.CASCADE,
        related_name="evidence",
        null=True,
        blank=True,
    )

    evidence_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="valid",
    )

    description = models.TextField(blank=True)

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"{self.requirement} - "
            f"{self.evidence_type}"
        )


class EvidenceInvalidation(models.Model):
    """An auditable record that a change made evidence no longer current."""

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
        related_name="invalidations",
    )

    triggering_changed_file = models.ForeignKey(
        ChangedFile,
        on_delete=models.CASCADE,
        related_name="triggered_invalidations",
    )

    reason = models.CharField(max_length=255)

    invalidated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evidence", "triggering_changed_file"],
                name="unique_evidence_invalidation_trigger",
            ),
        ]

    def __str__(self):
        return (
            f"Evidence {self.evidence_id} invalidated by "
            f"{self.triggering_changed_file.filename}"
        )


class Verification(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("partial", "Partial"),
        ("unverified", "Unverified"),
        ("stale", "Stale"),
        ("failed", "Failed"),
    ]

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="verifications",
    )

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name="verifications",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    summary = models.TextField(blank=True)

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    invalidated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requirement", "pull_request"],
                name="unique_requirement_pull_request_verification",
            ),
        ]

    def __str__(self):
        return (
            f"{self.requirement} - "
            f"{self.status}"
        )

class VerificationEvidence(models.Model):
    verification = models.ForeignKey(
        Verification,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )

    evidence = models.ForeignKey(
        Evidence,
        on_delete=models.CASCADE,
        related_name="verification_links",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["verification", "evidence"],
                name="unique_verification_evidence",
            ),
        ]
