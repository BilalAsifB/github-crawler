class CrawlerException(Exception):
    """Base exception for all crawler-related errors."""
    pass

class RateLimitExceededException(CrawlerException):
    """Raised when the GitHub GraphQL rate limit is hit."""
    def __init__(self, reset_at: str, message: str = "GitHub API rate limit exceeded."):
        self.reset_at = reset_at
        super().__init__(f"{message} Resets at: {reset_at}")

class DatabaseException(CrawlerException):
    """Raised when a database operation fails."""
    pass