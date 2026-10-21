import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain import display_name
from app.schemas import RequirementsInput


class StrictRecipeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def nonblank(value: str) -> str:
    if not value.strip() or any(
        unicodedata.category(char) == "Cc" and not char.isspace() for char in value
    ):
        raise ValueError("Text must be nonblank and contain no unsupported controls.")
    return value


class RecipeIngredient(StrictRecipeModel):
    name: str = Field(min_length=1, max_length=10000)
    quantity: float = Field(gt=0, le=100000, allow_inf_nan=False)
    unit: Literal["g", "ml", "tsp", "tbsp", "piece"]

    @field_validator("name")
    @classmethod
    def ingredient_name(cls, value):
        nonblank(value)
        if len(display_name(value)) > 100 or any(char in value for char in ",\r\n"):
            raise ValueError("Use one ingredient name of at most 100 cleaned characters.")
        return value


class RecipeCandidate(StrictRecipeModel):
    title: str = Field(min_length=1, max_length=160)
    servings: int = Field(ge=1, le=12)
    prep_minutes: int = Field(ge=0, le=240)
    cook_minutes: int = Field(ge=0, le=240)
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=50)
    instructions: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        min_length=1, max_length=30
    )

    @field_validator("title")
    @classmethod
    def title_text(cls, value):
        return nonblank(value)

    @field_validator("instructions")
    @classmethod
    def step_text(cls, values):
        return [nonblank(value) for value in values]

    @model_validator(mode="after")
    def positive_total_time(self):
        if self.prep_minutes + self.cook_minutes == 0:
            raise ValueError("Total recipe time must be positive.")
        return self


class CandidateBatch(StrictRecipeModel):
    recipes: list[RecipeCandidate] = Field(min_length=1, max_length=3)


class SuggestionsInput(RequirementsInput):
    source: Literal["sample", "openai", "groq"] = "sample"


class MatchedIngredient(BaseModel):
    name: str
    normalized_key: str
    quantity: float
    unit: str
    pantry_item_id: int | None


class RecipeWarning(BaseModel):
    code: Literal["PREFERRED_AVOID_PRESENT", "REQUIRED_AND_PREFERRED_AVOID"]
    ingredient_name: str
    message: str


class CheckedRecipe(BaseModel):
    recipe: RecipeCandidate
    in_pantry: list[MatchedIngredient]
    missing: list[MatchedIngredient]
    warnings: list[RecipeWarning]


class CandidateRejection(BaseModel):
    candidate_index: int
    codes: list[str]


class SuggestionsOutput(BaseModel):
    source: Literal["sample", "openai", "groq"]
    recipes: list[CheckedRecipe]
    rejected: list[CandidateRejection]
    check_scope: Literal["structure_and_ingredient_names_only"] = (
        "structure_and_ingredient_names_only"
    )
