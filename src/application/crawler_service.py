import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
import aiohttp

from src.infrastructure.github_client import GitHubGraphQLClient
from src.infrastructure.acl import GitHubTranslator
from src.infrastructure.database import PostgresRepository
from src.domain.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)

# GitHub GraphQL search returns at most 1,000 results per query
MAX_SEARCH_RESULTS = 1_000
INITIAL_MIN_STARS = 1
INITIAL_MAX_STARS = 1_000_000
INTER_REQUEST_DELAY = 1.0  # Seconds between requests to avoid secondary rate limits
MAX_CONSECUTIVE_ERRORS = 5
# Limit concurrent connections to avoid overwhelming GitHub's servers
CONNECTOR_LIMIT = 10
# Number of star-ranges crawled concurrently
MAX_CONCURRENT_RANGES = 3


class CrawlerService:
    """
    Service responsible for orchestrating the crawling of GitHub repositories,
    handling pagination, rate limits, and database interactions.

    Because GitHub's search API caps results at 1,000 per query, the crawler
    partitions the star-count space into sub-ranges and processes each one.
    """

    def __init__(
            self, 
            github_client: GitHubGraphQLClient,
            db_repository: PostgresRepository,
            target_count: int = 100_000
    ):
        self.github_client = github_client
        self.db_repository = db_repository
        self.target_count = target_count

    @staticmethod
    def _build_search_query(min_stars: int, max_stars: int) -> str:
        return f"stars:{min_stars}..{max_stars}"

    async def crawl(self) -> None:
        """
        Crawls GitHub repositories by partitioning the star-count space into
        ranges of ≤1,000 results each, bypassing the GitHub search API cap.

        Multiple ranges are crawled concurrently for maximum throughput.
        """
        self._total_fetched = 0
        self._lock = asyncio.Lock()
        ranges: deque[tuple[int, int]] = deque([(INITIAL_MIN_STARS, INITIAL_MAX_STARS)])

        logger.info(f"Starting crawl to fetch up to {self.target_count} repositories.")

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=CONNECTOR_LIMIT),
        ) as session:
            await self.github_client.validate_token(session)

            while ranges and self._total_fetched < self.target_count:
                # Launch up to MAX_CONCURRENT_RANGES workers at once
                batch: list[tuple[int, int]] = []
                while ranges and len(batch) < MAX_CONCURRENT_RANGES:
                    batch.append(ranges.popleft())

                tasks = [
                    self._crawl_range(session, self._build_search_query(lo, hi), lo, hi, ranges)
                    for lo, hi in batch
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, RateLimitExceededException):
                        reset_time = datetime.fromisoformat(result.reset_at.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        wait_seconds = max((reset_time - now).total_seconds() + 5, 1)
                        logger.warning(f"Rate limit exceeded. Waiting {wait_seconds:.0f}s until {result.reset_at}.")
                        await asyncio.sleep(wait_seconds)
                    elif isinstance(result, Exception):
                        logger.error(f"Unexpected error in range worker: {result}")

        logger.info(f"Crawling completed. Total repositories fetched: {self._total_fetched}.")

    async def _crawl_range(
        self, session, search_query, min_stars, max_stars, ranges,
    ) -> None:
        """Paginate through a single star-count range, splitting if it exceeds the API cap."""
        cursor = None
        consecutive_errors = 0

        while self._total_fetched < self.target_count:
            try:
                raw_nodes, next_cursor, has_next_page, repo_count = \
                    await self.github_client.fetch_page(session, cursor, search_query)

                # On the first page, check if this range needs splitting
                if cursor is None and repo_count > MAX_SEARCH_RESULTS and max_stars - min_stars > 0:
                    mid = (min_stars + max_stars) // 2
                    if mid > min_stars:
                        logger.info(
                            f"Range '{search_query}' has {repo_count} repos "
                            f"(>{MAX_SEARCH_RESULTS}). Splitting at {mid}."
                        )
                        async with self._lock:
                            ranges.appendleft((mid + 1, max_stars))
                            ranges.appendleft((min_stars, mid))
                        return

                consecutive_errors = 0

                if not raw_nodes:
                    break

                async with self._lock:
                    remaining = self.target_count - self._total_fetched
                    if remaining <= 0:
                        break
                    nodes_to_process = raw_nodes[:remaining]

                entities = [GitHubTranslator.to_domain(node) for node in nodes_to_process if node]
                await self.db_repository.bulk_upsert(entities)

                batch_size = len(entities)
                async with self._lock:
                    self._total_fetched += batch_size

                cursor = next_cursor

                logger.info(
                    f"[{search_query}] Fetched {batch_size}. "
                    f"Total: {self._total_fetched}/{self.target_count}."
                )

                if self._total_fetched >= self.target_count or not has_next_page:
                    break

                await asyncio.sleep(INTER_REQUEST_DELAY)

            except RateLimitExceededException:
                # Re-queue this range so it gets retried after the wait
                async with self._lock:
                    ranges.appendleft((min_stars, max_stars))
                raise

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"Too many consecutive errors for '{search_query}'. Skipping range.")
                    break
                wait = 10 * consecutive_errors
                logger.error(f"Error in '{search_query}': {e}. Retrying in {wait}s ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})...")
                await asyncio.sleep(wait)
