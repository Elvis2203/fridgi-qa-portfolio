"""Read-only recipe requirement checks for the local pantry owner."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import LOCAL_USER_ID
from app.domain import Entry, InvalidBatch, check_preferences, parse_batch
from app.models import Ingredient, IngredientAlias, PantryItem
from app.schemas import (
    PantryItemOutput,
    PreferenceOutput,
    RequirementsOutput,
    RequirementWarning,
)


class UnavailablePantryItems(ValueError):
    pass


class InvalidExclusions(ValueError):
    pass


class ConflictingRequirements(ValueError):
    pass


def parse_exclusions(text: str) -> list[Entry]:
    try:
        return parse_batch(text, allow_empty=True)
    except InvalidBatch as exc:
        raise InvalidExclusions(str(exc)) from exc


def check_requirements(
    session: Session,
    item_ids: list[int],
    entries: list[Entry],
    excluded: list[Entry] | None = None,
) -> RequirementsOutput:
    excluded = excluded or []
    ordered_ids = list(dict.fromkeys(item_ids))
    rows = session.scalars(
        select(PantryItem).where(
            PantryItem.user_id == LOCAL_USER_ID, PantryItem.id.in_(ordered_ids)
        )
    )
    by_id = {row.id: row for row in rows}
    if any(item_id not in by_id for item_id in ordered_ids):
        raise UnavailablePantryItems(
            "A selected ingredient is no longer available. Refresh your pantry selections."
        )
    required = [by_id[item_id] for item_id in ordered_ids]
    aliases = {
        key: Entry("", ingredient.display_name, ingredient.normalized_key)
        for key, ingredient in session.execute(
            select(IngredientAlias.normalized_key, Ingredient)
            .join(Ingredient, Ingredient.id == IngredientAlias.ingredient_id)
            .where(
                IngredientAlias.normalized_key.in_(
                    [entry.normalized_key for entry in entries + excluded]
                )
            )
        )
    }
    by_key = {row.normalized_key: row for row in required}
    result = check_preferences(entries, set(by_key), aliases)
    exclusions = check_preferences(excluded, set(by_key), aliases)
    if exclusions.overlaps:
        names = ", ".join(entry.display_name for entry in exclusions.overlaps)
        raise ConflictingRequirements(f"These ingredients are both required and excluded: {names}.")
    return RequirementsOutput(
        must_use=[PantryItemOutput.model_validate(row) for row in required],
        prefer_to_avoid=[
            PreferenceOutput(
                original_input=entry.original_input,
                display_name=entry.display_name,
                normalized_key=entry.normalized_key,
            )
            for entry in result.preferences
        ],
        excluded=[
            PreferenceOutput(
                original_input=entry.original_input,
                display_name=entry.display_name,
                normalized_key=entry.normalized_key,
            )
            for entry in exclusions.preferences
        ],
        warnings=[
            RequirementWarning(
                item_id=by_key[entry.normalized_key].id,
                display_name=entry.display_name,
                normalized_key=entry.normalized_key,
                message=(
                    f"{entry.display_name} is required and also preferred to avoid. "
                    "If you keep both, the must-use requirement takes priority."
                ),
            )
            for entry in result.overlaps
        ],
    )
