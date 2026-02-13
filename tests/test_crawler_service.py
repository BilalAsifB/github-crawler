import unittest
from unittest.mock import patch

from src.application.crawler_service import CrawlerService


class _FakeGitHubClient:
    def __init__(self, pages) -> None:
        self.pages = pages
        self.calls = 0

    async def fetch_page(self, session, cursor=None, search_query="", page_size=50):
        if self.calls >= len(self.pages):
            return [], None, False, 0
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
            ([node] * 6, "cursor-1", True, 12),
            ([node] * 6, None, False, 12),
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
        # repo_count <= 1000 so no splitting is triggered
        pages = [
            ([node] * 100000, None, False, 500),
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

    async def test_crawl_splits_large_range(self) -> None:
        """When a range has >1000 results, the crawler splits it."""
        node = {"id": "repo", "updatedAt": "2024-01-02T03:04:05Z"}

        class _SplittingClient:
            def __init__(self):
                self.queries = []

            async def fetch_page(self, session, cursor=None, search_query="", page_size=50):
                self.queries.append(search_query)
                if search_query == "stars:1000..1000000":
                    return [], None, False, 5000  # >1000 → triggers split
                return [node] * 5, None, False, 5

        client = _SplittingClient()
        db_repository = _FakeRepository()

        service = CrawlerService(
            github_client=client,
            db_repository=db_repository,
            target_count=10,
        )

        with patch(
            "src.application.crawler_service.GitHubTranslator.to_domain",
            return_value=object(),
        ):
            await service.crawl()

        # First call is the full range, then two sub-ranges after the split
        self.assertEqual(client.queries[0], "stars:1000..1000000")
        self.assertEqual(client.queries[1], "stars:1000..500500")
        self.assertEqual(client.queries[2], "stars:500501..1000000")
        self.assertEqual(db_repository.total_entities, 10)
