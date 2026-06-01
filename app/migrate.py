import logging

from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def run_migrations(conn: AsyncConnection) -> None:
    """Placeholder for future schema migrations. create_all handles v1 schema."""
    _ = conn
