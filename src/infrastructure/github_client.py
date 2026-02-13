import aiohttp
import asyncio
import logging
import random
from typing import Dict, Any, Tuple, List

from src.domain.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)

# The GraphQL query to fetch repositories with pagination.
# search_query and page_size are parameterised so the crawler can partition
# the star-count space and avoid the 1,000-result-per-query cap.
GRAPHQL_QUERY = """
query ($cursor: String, $searchQuery: String!, $pageSize: Int!) {
  search(query: $searchQuery, type: REPOSITORY, first: $pageSize, after: $cursor) {
    repositoryCount
    pageInfo {
      endCursor
      hasNextPage
    }
    nodes {
      ... on Repository {
        id
        name
        owner {
          login
        }
        stargazers {
          totalCount
        }
        updatedAt
      }
    }
  }
  rateLimit {
    cost
    remaining
    resetAt
  } 
}
"""

DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 5
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)
MAX_RETRIES = 7

class GitHubGraphQLClient:
    """
    Client for interacting with the GitHub GraphQL API.
    Handles authentication, query execution, and rate limit management.
    """

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-crawler-sofstica",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.api_url = "https://api.github.com/graphql"

    async def fetch_page(
        self,
        session: aiohttp.ClientSession,
        cursor: str = None,
        search_query: str = "stars:>=1000",
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Dict], str, bool, int]:
        """
        Fetches a single page of repositories from GitHub.

        Returns:
            Tuple of (nodes, end_cursor, has_next_page, repository_count).
        """
        current_page_size = page_size

        for attempt in range(MAX_RETRIES):
          payload = {
              "query": GRAPHQL_QUERY,
              "variables": {"cursor": cursor, "searchQuery": search_query, "pageSize": current_page_size},
          }
          try:
            async with session.post(self.api_url, json=payload, headers=self.headers, timeout=REQUEST_TIMEOUT) as response:
                # Handle secondary rate limit (abuse detection)
                if response.status == 403:
                  retry_after = response.headers.get('Retry-After')
                  sleep_time = int(retry_after) if retry_after else 60
                  logger.warning(f"Secondary rate limit (403). Sleeping {sleep_time}s...")
                  await asyncio.sleep(sleep_time)
                  continue

                if response.status in {500, 502, 503, 504}:
                  # Reduce page size on server errors — large pages cause GitHub timeouts
                  current_page_size = max(current_page_size // 2, MIN_PAGE_SIZE)
                  sleep_time = (2 ** attempt) + random.uniform(0, 2)
                  logger.warning(
                      f"Server error ({response.status}). "
                      f"Reducing page size to {current_page_size}, "
                      f"retrying in {sleep_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})..."
                  )
                  await asyncio.sleep(sleep_time)
                  continue

                response.raise_for_status()
                data = await response.json()

                # Handle GraphQL-level errors (can occur even with HTTP 200)
                if 'errors' in data:
                    error_msg = data['errors'][0].get('message', 'Unknown GraphQL error')
                    if 'data' not in data or data['data'] is None:
                        current_page_size = max(current_page_size // 2, MIN_PAGE_SIZE)
                        sleep_time = (2 ** attempt) + random.uniform(0, 2)
                        logger.warning(f"GraphQL error: {error_msg}. Retrying in {sleep_time:.1f}s...")
                        await asyncio.sleep(sleep_time)
                        continue
                    logger.warning(f"GraphQL partial error: {error_msg}")

                rate_limit = data.get('data', {}).get('rateLimit', {})
                remaining = rate_limit.get('remaining', 100)

                if remaining < 10:
                    reset_at = rate_limit.get('resetAt')
                    raise RateLimitExceededException(reset_at=reset_at)

                search_data = data.get('data', {}).get('search', {})
                nodes = search_data.get('nodes', [])
                page_info = search_data.get('pageInfo', {})
                repo_count = search_data.get('repositoryCount', 0)

                return nodes, page_info.get('endCursor'), page_info.get('hasNextPage', False), repo_count

          except (aiohttp.ClientError, asyncio.TimeoutError) as e:
              current_page_size = max(current_page_size // 2, MIN_PAGE_SIZE)
              sleep_time = (2 ** attempt) + random.uniform(0, 2)
              logger.warning(
                  f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                  f"Reducing page size to {current_page_size}, retrying in {sleep_time:.1f}s..."
              )
              await asyncio.sleep(sleep_time)

        raise Exception(f"Failed to fetch page after {MAX_RETRIES} attempts.")
