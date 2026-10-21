from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.db import LOCAL_USER_ID
from app.domain import NORMALIZATION_VERSION, Entry
from app.models import Ingredient, IngredientAlias, PantryItem
from app.schemas import BatchOutput, EntryResult, PantryItemOutput


def delete_item(session: Session, item_id: int) -> bool:
    deleted_id = session.scalar(
        delete(PantryItem)
        .where(PantryItem.id == item_id, PantryItem.user_id == LOCAL_USER_ID)
        .returning(PantryItem.id)
    )
    return deleted_id is not None


def list_items(session: Session) -> list[PantryItemOutput]:
    rows = session.scalars(
        select(PantryItem).where(PantryItem.user_id == LOCAL_USER_ID).order_by(PantryItem.id)
    )
    return [PantryItemOutput.model_validate(row) for row in rows]


def add_items(session: Session, entries: list[Entry]) -> BatchOutput:
    # Take SQLite's writer lock before reading aliases or inserting. Concurrent
    # submissions wait, then deduplicate against committed data in this transaction.
    session.connection().exec_driver_sql("UPDATE users SET id = id WHERE id = 1")
    results = []
    for index, entry in enumerate(entries, start=1):
        ingredient = session.scalar(
            select(Ingredient)
            .join(IngredientAlias, IngredientAlias.ingredient_id == Ingredient.id)
            .where(IngredientAlias.normalized_key == entry.normalized_key)
        )
        key = ingredient.normalized_key if ingredient else entry.normalized_key
        name = ingredient.display_name if ingredient else entry.display_name
        inserted_id = session.scalar(
            insert(PantryItem)
            .values(
                user_id=LOCAL_USER_ID,
                ingredient_id=ingredient.id if ingredient else None,
                original_input=entry.original_input,
                display_name=name,
                normalized_key=key,
                normalization_version=NORMALIZATION_VERSION,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "normalized_key"])
            .returning(PantryItem.id)
        )
        existing = session.scalar(
            select(PantryItem).where(
                PantryItem.user_id == LOCAL_USER_ID, PantryItem.normalized_key == key
            )
        )
        results.append(
            EntryResult(
                entry_index=index,
                original_input=entry.original_input,
                display_name=existing.display_name,
                item_id=existing.id,
                outcome="added" if inserted_id is not None else "skipped_duplicate",
            )
        )
    added = sum(result.outcome == "added" for result in results)
    return BatchOutput(
        added_count=added,
        skipped_count=len(results) - added,
        results=results,
        items=list_items(session),
    )
