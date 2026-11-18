from pathlib import Path

from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


DATABASE_PATH = Path(__file__).resolve().parent / "history.db"
DATABASE_URL = URL.create("sqlite", database=str(DATABASE_PATH))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def migrate_conversation_ownership() -> None:
    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        return

    column_names = {
        column["name"] for column in inspector.get_columns("conversations")
    }
    with engine.begin() as connection:
        if "user_id" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_id "
                "ON conversations (user_id)"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
