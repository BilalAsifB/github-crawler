import unittest
from unittest.mock import patch

from src.application.crawler_service import CrawlerService


class _FakeGitHubClient:
    def __init__(self, pages) -> None:
        self.pages = pages
        self.calls = 0

    async def fetch_page(self, session, cursor=None):
        if self.calls >= len(self.pages):
            raise AssertionError("fetch_page called more times than expected.")
        page = self.pages[self.calls]
        self.calls += 1
        return page


class _FakeRepository:
    def __init__(self) -> None:
        self.total_entities = 0

    async def bulk_upsert(self, entities) -> None:
        self.total_entities += len(entities)


class TestCrawlerService(unittest.IsolatedAsyncioTestCase):
    async def test_crawl_respects_ten_target(self) -> None:
        node = {"id": "repo", "updatedAt": "2024-01-02T03:04:05Z"}
        pages = [
            ([node] * 6, "cursor-1", True),
            ([node] * 6, None, False),
        ]
        github_client = _FakeGitHubClient(pages)
        db_repository = _FakeRepository()

        service = CrawlerService(
            github_client=github_client,
            db_repository=db_repository,
            target_count=10,
        )

        with patch(
            "src.application.crawler_service.GitHubTranslator.to_domain",
            return_value=object(),
        ):
            await service.crawl()

        self.assertEqual(db_repository.total_entities, 10)
        self.assertEqual(github_client.calls, 2)

    async def test_crawl_respects_hundred_thousand_target(self) -> None:
        node = {"id": "repo", "updatedAt": "2024-01-02T03:04:05Z"}
        pages = [
            ([node] * 100000, None, True),
        ]
        github_client = _FakeGitHubClient(pages)
        db_repository = _FakeRepository()

        service = CrawlerService(
            github_client=github_client,
            db_repository=db_repository,
            target_count=100000,
        )

        with patch(
            "src.application.crawler_service.GitHubTranslator.to_domain",
            return_value=object(),
        ):
            await service.crawl()

        self.assertEqual(db_repository.total_entities, 100000)
        self.assertEqual(github_client.calls, 1)
