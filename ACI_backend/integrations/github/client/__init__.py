import json
import requests

class GitHubAPIError(Exception):
    """Raised when a GitHub API request fails."""


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token=None):
        self.token = token
        self.session = requests.Session()

    def _request(self, endpoint):
        url = f"{self.BASE_URL}{endpoint}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = self.session.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_commit(self, owner, repository, sha):
        return self._request(f"/repos/{owner}/{repository}/commits/{sha}")

    def get_pull_request_commits(self, owner, repository, pull_request_number):
        endpoint = f"/repos/{owner}/{repository}/pulls/{pull_request_number}/commits"
        response = self.session.get(f"{self.BASE_URL}{endpoint}")
        response.raise_for_status()
        return response.json()
