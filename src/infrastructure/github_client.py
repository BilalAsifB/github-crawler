import aiohttp
from typing import Dict, Any, Tuple, List
from src.domain.exceptions import RateLimitExceededException

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

        async with session.post(self.api_url, json=payload, headers=self.headers) as response:
            # Handle standard HTTP errors
            response.raise_for_status()

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
