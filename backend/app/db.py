import os
from pathlib import Path

from sqlalchemy import create_engine, event

DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "fridgi.db"
LOCAL_USER_ID = 1


def database_url() -> str:
    return os.environ.get("FRIDGI_DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE.as_posix()}")


def make_engine(url: str):
    if not url.startswith("sqlite:///"):
        raise ValueError("Story 1 supports local SQLite only.")
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        # Explicit SQLAlchemy BEGIN avoids sqlite3 legacy transaction surprises.
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    return engine
