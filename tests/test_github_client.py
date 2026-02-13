import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.github_client import GitHubGraphQLClient


class TestGitHubGraphQLClient(unittest.TestCase):
    def test_headers_are_dict(self) -> None:
        token = "test-token"
        client = GitHubGraphQLClient(token=token)

        self.assertIsInstance(client.headers, dict)
        self.assertEqual(client.headers["Authorization"], f"Bearer {token}")

    def test_headers_include_user_agent(self) -> None:
        client = GitHubGraphQLClient(token="t")
        self.assertIn("User-Agent", client.headers)
        self.assertIn("Accept", client.headers)


class TestSecondaryRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_403_retry_after_is_respected(self) -> None:
        """When GitHub returns 403 + Retry-After, the client sleeps and retries."""
        client = GitHubGraphQLClient(token="test-token")

        # First response: 403 with Retry-After header
        resp_403 = AsyncMock()
        resp_403.status = 403
        resp_403.headers = {"Retry-After": "1"}
        resp_403.__aenter__ = AsyncMock(return_value=resp_403)
        resp_403.__aexit__ = AsyncMock(return_value=False)

        # Second response: 200 with valid data
        resp_200 = AsyncMock()
        resp_200.status = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.json = AsyncMock(return_value={
            "data": {
                "search": {
                    "repositoryCount": 5,
                    "pageInfo": {"endCursor": "abc", "hasNextPage": False},
                    "nodes": [{"id": "1"}],
                },
                "rateLimit": {"remaining": 4999, "resetAt": "2026-01-01T00:00:00Z"},
            }
        })
        resp_200.__aenter__ = AsyncMock(return_value=resp_200)
        resp_200.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.post = MagicMock(side_effect=[resp_403, resp_200])

        with patch("src.infrastructure.github_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            nodes, cursor, has_next, count = await client.fetch_page(session)

        # Should have slept for the Retry-After value (1 second)
        mock_sleep.assert_any_call(1)
        self.assertEqual(nodes, [{"id": "1"}])
        self.assertEqual(count, 5)
