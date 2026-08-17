import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class GitHubAPIError(Exception):
    """Raised when a GitHub API request fails."""


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token=None):
        self.token = token

    def _request(self, endpoint):
        url = f"{self.BASE_URL}{endpoint}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(
            url,
            headers=headers,
            method="GET",
        )

        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode())

        except HTTPError as exc:
            raise GitHubAPIError(
                f"GitHub API returned {exc.code}"
            ) from exc

        except URLError as exc:
            raise GitHubAPIError(
                "Unable to connect to GitHub API."
            ) from exc

    def get_commit(self, owner, repository, sha):
        return self._request(
            f"/repos/{owner}/{repository}/commits/{sha}"
        )