from unittest.mock import patch

import pytest

from ACI_backend.integrations.github.client import GitHubClient


@pytest.fixture
def github_client():
    return GitHubClient(token="test-token")


def test_get_commit_returns_github_commit(github_client):
    github_response = {
        "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "files": [
            {
                "filename": "users/views.py",
                "status": "modified",
                "additions": 10,
                "deletions": 3,
                "changes": 13,
                "patch": "@@ -1,3 +1,10 @@",
            }
        ],
    }

    with patch.object(
        github_client,
        "_request",
        return_value=github_response,
    ) as mock_request:

        result = github_client.get_commit(
            "kilel",
            "aci-demo",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )

    assert result == github_response

    mock_request.assert_called_once_with(
        "/repos/kilel/aci-demo/commits/"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )