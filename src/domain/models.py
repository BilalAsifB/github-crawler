from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class RepositoryEntity(BaseModel):
    """
    Immutable domain model representing a GitHub Repository.
    This is the core entity used throughout the application.
    """
    # Enforces immutability: once created, fields cannot be modified.
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="The unique GraphQL Node ID from GitHub")
    name: str = Field(..., description="Name of the repository")
    owner: str = Field(..., description="Login name of the repository owner")
    stars: int = Field(..., ge=0, description="Total number of stargazers")
    updated_at: datetime = Field(..., description="Timestamp of the last update")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Flexible JSON payload for future metadata (issues, PRs, etc.)"
    )