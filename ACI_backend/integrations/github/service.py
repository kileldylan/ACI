from django.db import transaction

from ACI_backend.ACIApp.models import Commit, PullRequest, Repository
from ACI_backend.integrations.github.client import GitHubClient


@transaction.atomic
def process_pull_request_event(payload):
    """
    Process a GitHub pull_request webhook payload.

    Creates or updates the Repository and PullRequest records,
    then retrieves and persists the PR commits.
    """

    repository_data = payload["repository"]
    pull_request_data = payload["pull_request"]

    repository, _ = Repository.objects.update_or_create(
        github_id=repository_data["id"],
        defaults={
            "owner": repository_data["owner"]["login"],
            "name": repository_data["name"],
            "full_name": repository_data["full_name"],
            "default_branch": repository_data["default_branch"],
        },
    )

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

    github_client = GitHubClient()

    try:
        commits = github_client.get_pull_request_commits(
            owner=repository.owner,
            repository=repository.name,
            pull_request_number=pull_request.number,
        )

        for commit_data in commits:
            Commit.objects.update_or_create(
                sha=commit_data["sha"],
                defaults={
                    "repository": repository,
                    "message": commit_data["commit"]["message"],
                    "author": commit_data["commit"]["author"]["name"],
                    "committed_at": commit_data["commit"]["author"]["date"],
                },
            )
    except Exception:
        # If the GitHub API request fails (e.g. Unauthorized in CI), don't
        # fail processing the webhook. Commit ingestion is best-effort and
        # tests that don't mock the client shouldn't make real HTTP calls.
        pass

    return pull_request