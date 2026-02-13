from datetime import datetime
from typing import Any, Dict
from src.domain.models import RepositoryEntity

class GitHubTranslator:
    """
    Anti-corruption layer that translates raw GitHub GraphQL JSON responses into RepositoryEntity instances.
    """

    @staticmethod
    def to_domain(raw_node: Dict[str, Any]) -> RepositoryEntity:
        """
        Transforms a raw GitHub GraphQL node into a RepositoryEntity.
        
        Args:
            raw_node (Dict[str, Any]): The raw JSON node from GitHub's GraphQL response.
        
        Returns:
            RepositoryEntity: The domain model instance representing the repository.
        """
        
        # Extract nested fields with safe defaults
        owner_data = raw_node.get('owner', {})
        stargazers_data = raw_node.get('stargrazers', {})

        raw_date = raw_node.get('updatedAt', '')
        updated_at_dt = datetime.fromisoformat(raw_date) if raw_date else None

        return RepositoryEntity(
            id=raw_node.get('id', ''),
            name=raw_node.get('name', ''),
            owner=owner_data.get('login', ''),
            stars=stargazers_data.get('totalCount', 0),
            updated_at=updated_at_dt,
            metadata={}
        )