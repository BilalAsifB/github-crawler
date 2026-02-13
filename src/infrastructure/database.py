from typing import List
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import Table, Column, String, Integer, DateTime, MetaData, text
from src.domain.models import RepositoryEntity

# SQLAlchemy core Table definition
metadata = MetaData()
repos_table = Table(
    'github_repositories', metadata,
    Column('id', String, primary_key=True),
    Column('name', String, nullable=False),
    Column('owner', String, nullable=False),
    Column('stars', Integer, nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False),
)

class PostgresRepository:
    """
    Repository class for interacting with the PostgreSQL database.
    Handles batch insertion of RepositoryEntity instances.
    """

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)

    async def bulk_upsert(self, entities: List[RepositoryEntity]) -> None:
        """
        Inserts multiple RepositoryEntity instances into the database in a single batch operation.
        
        Args:
            entities (List[RepositoryEntity]): List of repository entities to insert.
        """
        if not entities:
            return  # No entities to insert
        
        values = [
            {   'id': entity.id,
                'name': entity.name,
                'owner': entity.owner,
                'stars': entity.stars,
                'updated_at': entity.updated_at,
            } for entity in entities
        ]

        async with self.engine.begin() as conn:
            stmt = insert(repos_table).values(values)

            # Only update if the incoming star count is different from the existing one.  
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_={
                    'stars': stmt.excluded.stars,
                    'updated_at': text('NOW()'),
                },
                where=(repos_table.c.stars.is_distinct_from(stmt.excluded.stars) | repos_table.c.updated_at.is_distinct_from(stmt.excluded.updated_at))
            )

            await conn.execute(upsert_stmt)