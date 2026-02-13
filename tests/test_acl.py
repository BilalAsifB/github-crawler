import unittest
from datetime import datetime, timezone

from src.infrastructure.acl import GitHubTranslator


class TestGitHubTranslator(unittest.TestCase):
    def test_to_domain_parses_stargazers_and_updated_at(self) -> None:
        raw_node = {
            "id": "repo-1",
            "name": "example",
            "owner": {"login": "octocat"},
            "stargazers": {"totalCount": 123},
            "updatedAt": "2024-01-02T03:04:05Z",
        }

        entity = GitHubTranslator.to_domain(raw_node)

        self.assertEqual(entity.stars, 123)
        self.assertEqual(entity.owner, "octocat")
        self.assertEqual(
            entity.updated_at,
            datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    def test_missing_updated_at_raises(self) -> None:
        raw_node = {
            "id": "repo-1",
            "name": "example",
            "owner": {"login": "octocat"},
            "stargazers": {"totalCount": 123},
        }

        with self.assertRaises(ValueError):
            GitHubTranslator.to_domain(raw_node)
