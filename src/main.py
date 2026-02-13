import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

from src.infrastructure.github_client import GitHubGraphQLClient
from src.infrastructure.database import PostgresRepository
from src.application.crawler_service import CrawlerService

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    # Load environment variables from .env file
    load_dotenv()

    # Get GitHub token and database URL from environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    db_url = os.getenv("DATABASE_URL")

    if not github_token:
        logger.error("GITHUB_TOKEN is not set in the environment.")
        sys.exit(1)  

    if not db_url:
        logger.error("DATABASE_URL is not set in the environment.")
        sys.exit(1)

    # Initialize the GitHub client and database repository
    github_client = GitHubGraphQLClient(token=github_token)
    db_repository = PostgresRepository(db_url=db_url)

    # Create the crawler service and start crawling
    crawler_service = CrawlerService(
        github_client=github_client, 
        db_repository=db_repository,
        target_count=100_000
    )

    try:
        await crawler_service.crawl()
    except KeyboardInterrupt:
        logger.info("Crawl interrupted by user. Exiting gracefully.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")  
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
