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
    """A Git commit associated with a repository."""

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="commits",
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