from alembic import context

from app.db import DEFAULT_DATABASE, database_url, make_engine
from app.models import Base

config = context.config
url = config.attributes.get("database_url") or database_url()

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    if url == f"sqlite:///{DEFAULT_DATABASE.as_posix()}":
        DEFAULT_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
