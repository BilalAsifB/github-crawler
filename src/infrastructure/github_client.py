import aiohttp
import asyncio
import logging
from typing import Dict, Any, Tuple, List
from domain.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)

# The GraphQL query to fetch repositories with pagination
GRAPHQL_QUERY = """
query ($cursor: String) {
  search(query: "stars:>1000", type: REPOSITORY, first: 100, after: $cursor) {
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

class GitHubGraphQLClient:
    """
    Client for interacting with the GitHub GraphQL API.
    Handles authentication, query execution, and rate limit management.
    """

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}"
        }
        self.api_url = "https://api.github.com/graphql"

    async def fetch_page(self, session: aiohttp.ClientSession, cursor: str = None) -> Tuple[List[Dict], str, bool]:
        """
        Fetches a single page of repositories from GitHub.
        
        Args:
            session (aiohttp.ClientSession): The HTTP session to use for the request.
            cursor (str, optional): The pagination cursor for fetching the next page. Defaults to None.
        
        Returns:
            Tuple[List[Dict], str, bool]: A tuple containing the list of repository nodes, the next cursor, and a boolean indicating if there are more pages.
        """

        payload = {
            "query": GRAPHQL_QUERY,
            "variables": {"cursor": cursor}
        }
        max_retries = 5

        for attempt in range(max_retries):
          try:
            async with session.post(self.api_url, json=payload, headers=self.headers) as response:
                # Handle standard HTTP errors
                if response.status in {500, 502, 503, 504}:
                  sleep_time = 2 ** attempt  # Exponential backoff
                  logger.warning(f"Server error (status {response.status}). Retrying in {sleep_time} seconds...")
                  await asyncio.sleep(sleep_time)
                  continue  # Retry the request
                
                response.raise_for_status()  # Raise an exception for non-200 responses

                data = await response.json()

                # Enforce rate limits
                rate_limit = data.get('data', {}).get('rateLimit', {})
                remaning = rate_limit.get('remaining', 100)

                if remaning < 10: # Threshold to prevent hitting the limit
                    reset_at = rate_limit.get('resetAt')
                    raise RateLimitExceededException(reset_at=reset_at)
                
                # Extract repositories and pagination info
                search_data = data.get('data', {}).get('search', {})
                nodes = search_data.get('nodes', [])
                page_info = search_data.get('pageInfo', {})

                end_cursor = page_info.get('endCursor')
                has_next_page = page_info.get('hasNextPage', False)

                return nodes, end_cursor, has_next_page
            
          except aiohttp.ClientError as e:
              sleep_time = 2 ** attempt  # Exponential backoff
              logger.warning(f"HTTP request failed (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {sleep_time} seconds...")
              await asyncio.sleep(sleep_time)  # Wait before retrying
              
        raise Exception(f"Failed to fetch page after {max_retries} attempts.")