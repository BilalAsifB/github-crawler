import unittest

from src.infrastructure.github_client import GitHubGraphQLClient


class TestGitHubGraphQLClient(unittest.TestCase):
    def test_headers_are_dict(self) -> None:
        token = "test-token"
        client = GitHubGraphQLClient(token=token)

        self.assertIsInstance(client.headers, dict)
        self.assertEqual(client.headers["Authorization"], f"Bearer {token}")
