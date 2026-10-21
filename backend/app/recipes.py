"""Independent validation. Provider text never determines pantry membership."""

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import Entry, comparison_key, display_name, parse_batch
from app.models import Ingredient, IngredientAlias
from app.pantry import list_items
from app.recipe_models import (
    CandidateRejection,
    CheckedRecipe,
    MatchedIngredient,
    RecipeCandidate,
    RecipeWarning,
    SuggestionsInput,
    SuggestionsOutput,
)
from app.requirements import check_requirements, parse_exclusions
from app.schemas import PantryItemOutput, RequirementsOutput


@dataclass
class RecipeContext:
    pantry: list[PantryItemOutput]
    requirements: RequirementsOutput
    aliases: dict[str, Entry]

    def provider_input(self):
        return {
            "pantry": [item.display_name for item in self.pantry],
            "must_use": [item.display_name for item in self.requirements.must_use],
            "prefer_to_avoid": [item.display_name for item in self.requirements.prefer_to_avoid],
            "do_not_use": [item.display_name for item in self.requirements.excluded],
            "extra_ingredients_allowed": True,
        }


class RecipeContextTooLarge(ValueError):
    pass


class InvalidRecipeOutput(ValueError):
    def __init__(self, message: str, codes: list[str] | None = None):
        super().__init__(message)
        self.codes = codes or []


def load_context(session: Session, body: SuggestionsInput) -> RecipeContext:
    entries = parse_batch(body.prefer_to_avoid_text, allow_empty=True)
    requirements = check_requirements(
        session, body.must_use_item_ids, entries, parse_exclusions(body.excluded_text)
    )
    pantry = list_items(session)
    if len(pantry) > 500:
        raise RecipeContextTooLarge("Recipe requests currently support at most 500 pantry entries.")
    aliases = {
        key: Entry("", ingredient.display_name, ingredient.normalized_key)
        for key, ingredient in session.execute(
            select(IngredientAlias.normalized_key, Ingredient).join(
                Ingredient, Ingredient.id == IngredientAlias.ingredient_id
            )
        )
    }
    return RecipeContext(pantry, requirements, aliases)


def validate_candidates(payload: object, context: RecipeContext, source: str) -> SuggestionsOutput:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"recipes"}
        or not isinstance(payload["recipes"], list)
        or not 1 <= len(payload["recipes"]) <= 3
    ):
        raise InvalidRecipeOutput("The recipe source returned an invalid response structure.")
    required = {item.normalized_key for item in context.requirements.must_use}
    avoided = {item.normalized_key for item in context.requirements.prefer_to_avoid}
    excluded = {item.normalized_key for item in context.requirements.excluded}
    pantry = {item.normalized_key: item for item in context.pantry}
    accepted, rejected = [], []
    for index, raw in enumerate(payload["recipes"], start=1):
        try:
            recipe = RecipeCandidate.model_validate(raw)
        except ValidationError:
            rejected.append(CandidateRejection(candidate_index=index, codes=["INVALID_STRUCTURE"]))
            continue
        seen, matches, warnings, codes = set(), [], [], []
        for item in recipe.ingredients:
            key = comparison_key(item.name)
            identity = context.aliases.get(key, Entry(item.name, display_name(item.name), key))
            key = identity.normalized_key
            if key in seen and "DUPLICATE_INGREDIENT" not in codes:
                codes.append("DUPLICATE_INGREDIENT")
            seen.add(key)
            matches.append(
                MatchedIngredient(
                    name=identity.display_name,
                    normalized_key=key,
                    quantity=item.quantity,
                    unit=item.unit,
                    pantry_item_id=pantry[key].id if key in pantry else None,
                )
            )
            if key in avoided:
                is_required = key in required
                warnings.append(
                    RecipeWarning(
                        code="REQUIRED_AND_PREFERRED_AVOID"
                        if is_required
                        else "PREFERRED_AVOID_PRESENT",
                        ingredient_name=identity.display_name,
                        message=(
                            f"{identity.display_name} matches an avoidance preference. "
                            + (
                                "It is also required, so must-use takes priority."
                                if is_required
                                else "This suggestion does not meet that preference."
                            )
                        ),
                    )
                )
        if required - seen:
            codes.append("MISSING_REQUIRED_INGREDIENT")
        if excluded & seen:
            codes.append("EXCLUDED_INGREDIENT_PRESENT")
        if codes:
            rejected.append(CandidateRejection(candidate_index=index, codes=codes))
        else:
            accepted.append(
                CheckedRecipe(
                    recipe=recipe,
                    in_pantry=[item for item in matches if item.pantry_item_id is not None],
                    missing=[item for item in matches if item.pantry_item_id is None],
                    warnings=warnings,
                )
            )
    if not accepted:
        reasons = sorted({code for rejection in rejected for code in rejection.codes})
        raise InvalidRecipeOutput(
            "The sample did not meet all ingredient requirements and recipe checks. "
            "Review your selections. The fixed sample only contains "
            "Greek yogurt, apple, and oats."
            if source == "sample"
            else "No generated recipe met all ingredient requirements and recipe checks. "
            "Please review your requirements before trying again.",
            codes=reasons,
        )
    return SuggestionsOutput(source=source, recipes=accepted, rejected=rejected)
