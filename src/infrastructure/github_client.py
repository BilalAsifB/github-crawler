import aiohttp
import asyncio
import logging
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

DEFAULT_PAGE_SIZE = 50
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

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
        payload = {
            "query": GRAPHQL_QUERY,
            "variables": {"cursor": cursor, "searchQuery": search_query, "pageSize": page_size},
        }
        max_retries = 5

        for attempt in range(max_retries):
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
                  sleep_time = 2 ** attempt
                  logger.warning(f"Server error (status {response.status}). Retrying in {sleep_time}s...")
                  await asyncio.sleep(sleep_time)
                  continue

                response.raise_for_status()
                data = await response.json()

                # Handle GraphQL-level errors (can occur even with HTTP 200)
                if 'errors' in data:
                    error_msg = data['errors'][0].get('message', 'Unknown GraphQL error')
                    if 'data' not in data or data['data'] is None:
                        sleep_time = 2 ** attempt
                        logger.warning(f"GraphQL error: {error_msg}. Retrying in {sleep_time}s...")
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

          except aiohttp.ClientError as e:
              sleep_time = 2 ** attempt
              logger.warning(f"HTTP error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {sleep_time}s...")
              await asyncio.sleep(sleep_time)

        raise Exception(f"Failed to fetch page after {max_retries} attempts.")
