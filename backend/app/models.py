from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))


class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    normalized_key: Mapped[str] = mapped_column(String(300), unique=True)


class IngredientAlias(Base):
    __tablename__ = "ingredient_aliases"
    normalized_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))


class PantryItem(Base):
    __tablename__ = "pantry_items"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_key", name="uq_pantry_owner_key"),
        CheckConstraint("length(display_name) BETWEEN 1 AND 100", name="ck_pantry_name_length"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id"), nullable=True)
    original_input: Mapped[str] = mapped_column(String(10000))
    display_name: Mapped[str] = mapped_column(String(100))
    normalized_key: Mapped[str] = mapped_column(String(300))
    normalization_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
