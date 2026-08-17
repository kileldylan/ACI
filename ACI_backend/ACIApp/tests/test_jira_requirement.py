from unittest.mock import Mock

import pytest

from ACI_backend.ACIApp.models import (
    PullRequest,
    Repository,
    Requirement,
    RequirementPullRequest,
)
from ACI_backend.integrations.jira.service import (
    ingest_jira_requirement,
    ingest_jira_requirements_for_pull_request,
)
from ACI_backend.integrations.jira.utils import (
    extract_jira_issue_keys,
)


@pytest.mark.django_db
def test_ingest_jira_requirement_creates_requirement_and_links_pr():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Add authentication",
        author="kilel",
        source_branch="feature/auth",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    jira_issue = {
        "key": "PROJ-123",
        "fields": {
            "summary": "Add authentication",
            "description": "Users must be able to authenticate.",
            "status": {
                "name": "To Do",
            },
        },
    }

    requirement = ingest_jira_requirement(
        pull_request=pull_request,
        jira_issue=jira_issue,
    )

    assert requirement.external_id == "PROJ-123"
    assert requirement.source == "jira"
    assert requirement.title == "Add authentication"
    assert requirement.description == (
        "Users must be able to authenticate."
    )
    assert requirement.status == "open"

    assert Requirement.objects.count() == 1

    link = RequirementPullRequest.objects.get(
        requirement=requirement,
        pull_request=pull_request,
    )

    assert link.requirement == requirement
    assert link.pull_request == pull_request


def test_extract_jira_issue_keys():
    text = """
    Implements PROJ-123.
    Also addresses PROJ-456.
    """

    result = extract_jira_issue_keys(text)

    assert result == [
        "PROJ-123",
        "PROJ-456",
    ]


def test_extract_jira_issue_keys_removes_duplicates():
    text = """
    PROJ-123 is the main requirement.
    This PR also fixes PROJ-123.
    """

    result = extract_jira_issue_keys(text)

    assert result == ["PROJ-123"]


def test_extract_jira_issue_keys_returns_empty_for_no_match():
    text = "Fix authentication and improve error handling."

    result = extract_jira_issue_keys(text)

    assert result == []


@pytest.mark.django_db
def test_ingest_jira_requirements_for_pull_request():
    repository = Repository.objects.create(
        github_id=123456,
        owner="kilel",
        name="aci-demo",
        full_name="kilel/aci-demo",
        default_branch="main",
    )

    pull_request = PullRequest.objects.create(
        repository=repository,
        github_id=987654,
        number=1,
        title="Add authentication PROJ-123",
        author="kilel",
        source_branch="feature/auth",
        target_branch="main",
        base_sha="b" * 40,
        head_sha="a" * 40,
        state="open",
        is_merged=False,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-17T10:00:00Z",
    )

    jira_client = Mock()

    jira_client.get_issue.return_value = {
        "key": "PROJ-123",
        "fields": {
            "summary": "Add authentication",
            "description": (
                "Users must be able to authenticate."
            ),
            "status": {
                "name": "To Do",
            },
        },
    }

    requirements = ingest_jira_requirements_for_pull_request(
        pull_request=pull_request,
        text=pull_request.title,
        jira_client=jira_client,
    )

    assert len(requirements) == 1

    requirement = requirements[0]

    assert requirement.external_id == "PROJ-123"
    assert requirement.source == "jira"
    assert requirement.title == "Add authentication"

    assert Requirement.objects.count() == 1

    assert RequirementPullRequest.objects.filter(
        requirement=requirement,
        pull_request=pull_request,
    ).exists()

    jira_client.get_issue.assert_called_once_with(
        "PROJ-123",
    )