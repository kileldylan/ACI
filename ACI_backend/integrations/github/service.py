from django.db import transaction

from ACI_backend.ACIApp.models import (
    ChangedFile,
    Commit,
    PullRequest,
    Repository,
)
from ACI_backend.integrations.github.client import GitHubClient
from ACI_backend.integrations.verification.service import (
    invalidate_evidence_for_changed_file,
)


@transaction.atomic
def process_pull_request_event(payload):
    """
    Process a GitHub pull_request webhook payload.

    Creates or updates the Repository and PullRequest records,
    then retrieves and persists the PR commits.
    """

    repository_data = payload["repository"]
    pull_request_data = payload["pull_request"]

    # ---------------------------------------------------------
    # 1. Create or update repository
    # ---------------------------------------------------------

    repository, _ = Repository.objects.update_or_create(
        github_id=repository_data["id"],
        defaults={
            "owner": repository_data["owner"]["login"],
            "name": repository_data["name"],
            "full_name": repository_data["full_name"],
            "default_branch": repository_data["default_branch"],
        },
    )

    # ---------------------------------------------------------
    # 2. Create or update pull request
    # ---------------------------------------------------------

    pull_request, _ = PullRequest.objects.update_or_create(
        repository=repository,
        number=pull_request_data["number"],
        defaults={
            "github_id": pull_request_data["id"],
            "title": pull_request_data["title"],
            "author": pull_request_data["user"]["login"],
            "source_branch": pull_request_data["head"]["ref"],
            "target_branch": pull_request_data["base"]["ref"],
            "base_sha": pull_request_data["base"]["sha"],
            "head_sha": pull_request_data["head"]["sha"],
            "state": pull_request_data["state"],
            "is_merged": pull_request_data["merged"],
            "created_at": pull_request_data["created_at"],
            "updated_at": pull_request_data["updated_at"],
        },
    )

    # ---------------------------------------------------------
    # 3. Retrieve commits from GitHub
    # ---------------------------------------------------------

    github_client = GitHubClient()

    commits = github_client.get_pull_request_commits(
        owner=repository.owner,
        repository=repository.name,
        pull_request_number=pull_request.number,
    )

    # ---------------------------------------------------------
    # 4. Persist commits
    # ---------------------------------------------------------

    for commit_data in commits:
        commit, _ = Commit.objects.update_or_create(
            sha=commit_data["sha"],
            defaults={
                "repository": repository,
                "pull_request": pull_request,
                "message": commit_data["commit"]["message"],
                "author": commit_data["commit"]["author"]["name"],
                "committed_at": commit_data["commit"]["author"]["date"],
            },
        )

        # The pull-request commits endpoint does not include changed files.
        # Fetch the full commit so the change graph can be persisted and used
        # for evidence invalidation.
        github_commit = github_client.get_commit(
            owner=repository.owner,
            repository=repository.name,
            sha=commit.sha,
        )

        for changed_file in ingest_commit_files(
            commit=commit,
            github_commit=github_commit,
        ):
            invalidate_evidence_for_changed_file(changed_file)

    return pull_request


def ingest_commit_files(commit, github_commit):
    """
    Persist files changed by a GitHub commit.

    Uses update_or_create so repeated GitHub webhook deliveries
    do not create duplicate ChangedFile records.
    """

    files = github_commit.get("files", [])

    changed_files = []

    for file_data in files:
        changed_file, _ = ChangedFile.objects.update_or_create(
            commit=commit,
            filename=file_data["filename"],
            defaults={
                "status": file_data.get("status", ""),
                "additions": file_data.get("additions", 0),
                "deletions": file_data.get("deletions", 0),
                "changes": file_data.get("changes", 0),
                "patch": file_data.get("patch", ""),
            },
        )

        changed_files.append(changed_file)

    return changed_files
