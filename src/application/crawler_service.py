import asyncio
import logging
from datetime import datetime, timezone
import aiohttp

from infrastructure.github_client import GitHubGraphQLClient
from infrastructure.acl import GitHubTranslator
from infrastructure.database import PostgresRepository
from domain.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)

class CrawlerService:
    """
    Service responsible for orchestrating the crawling of GitHub repositories,
    handling pagination, rate limits, and database interactions.
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

    async def crawl(self) -> None:
        """
        Main method to start the crawling process. It handles pagination, rate limits,
        and batch database insertion until the target count of repositories is reached.
        """
        total_fetched = 0
        cursor = None

        logger.info(f"Starting crawl to fetch up to {self.target_count} repositories.")

        # Use a single HTTP session for the entire crawl to improve performance and reduce overhead
        async with aiohttp.ClientSession() as session:
            while total_fetched < self.target_count:
                try:
                    # Fetch raw data from GitHub
                    raw_nodes, next_cursor, has_next_page = await self.github_client.fetch_page(session, cursor)
                    if not raw_nodes:
                        logger.warning("No more repositories found. Ending crawl.")
                        break
                    
                    remaining = self.target_count - total_fetched
                    nodes_to_process = raw_nodes[:remaining]

                    # Translate raw data to domain entities and batch insert into the database
                    entities = [GitHubTranslator.to_domain(node) for node in nodes_to_process if node]
                    await self.db_repository.bulk_upsert(entities)

                    batch_size = len(entities)
                    total_fetched += batch_size
                    cursor = next_cursor

                    logger.info(f"Fetched {batch_size} repositories. Total so far: {total_fetched}/{self.target_count}.")

                    if total_fetched >= self.target_count:
                        logger.info("Target repository count reached. Ending crawl.")
                        break

                    if not has_next_page:
                        logger.info("Reached the end of available pages. Ending crawl.")
                        break

                except RateLimitExceededException as e:
                    # Calculate how long to wait until the rate limit resets and sleep for that duration
                    reset_time = datetime.fromisoformat(e.reset_at.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    wait_seconds = (reset_time - now).total_seconds() + 5 # Add a buffer to ensure the limit has reset
                    
                    if wait_seconds > 0:
                        logger.warning(f"Rate limit exceeded. Waiting for {wait_seconds:.2f} seconds until reset at {e.reset_at}.")
                        await asyncio.sleep(wait_seconds) 
                    else:
                        logger.warning("Rate limit reset time has already passed. Retrying immediately.")
                        await asyncio.sleep(1)  # Short wait before retrying

                except Exception as e:
                    logger.error(f"An error occurred during crawling: {str(e)}", exc_info=True)
                    await asyncio.sleep(5)  # Wait before retrying to avoid rapid failure loops

        logger.info(f"Crawling completed. Total repositories fetched: {total_fetched}.")
