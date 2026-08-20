from unittest.mock import Mock, patch

import pytest

from ACI_backend.integrations.github.client import GitHubClient


@pytest.mark.django_db
def test_get_pull_request_commits():
    github_response = [
        {
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "commit": {
                "message": "Add authentication",
                "author": {
                    "name": "kilel",
                },
            },
        }
    ]

    with patch(
        "ACI_backend.integrations.github.client.requests.Session.get"
    ) as mock_get:

        mock_response = Mock()
        mock_response.json.return_value = github_response
        mock_response.raise_for_status.return_value = None

        mock_get.return_value = mock_response

        client = GitHubClient()

        commits = client.get_pull_request_commits(
            owner="kilel",
            repository="aci-demo",
            pull_request_number=1,
        )

    mock_get.assert_called_once_with(
        "https://api.github.com/repos/"
        "kilel/aci-demo/pulls/1/commits",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=15,
    )

    assert commits == github_response