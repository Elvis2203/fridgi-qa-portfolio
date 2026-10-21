from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(max_length=10000, description="Comma or newline separated ingredient names.")


class PantryItemOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ingredient_id: int | None
    original_input: str
    display_name: str
    normalized_key: str
    normalization_version: int
    created_at: datetime


class PantryOutput(BaseModel):
    items: list[PantryItemOutput]


class EntryResult(BaseModel):
    entry_index: int
    original_input: str
    display_name: str
    item_id: int
    outcome: str


class BatchOutput(PantryOutput):
    added_count: int
    skipped_count: int
    results: list[EntryResult]


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    entry_index: int | None = None
    request_id: str
    reason_codes: list[str] | None = None


class ErrorOutput(BaseModel):
    error: ErrorDetail


class RequirementsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    must_use_item_ids: list[Annotated[int, Field(gt=0, le=9223372036854775807)]] = Field(
        default_factory=list, max_length=50
    )
    prefer_to_avoid_text: str = Field(default="", max_length=10000)
    excluded_text: str = Field(default="", max_length=10000)


class PreferenceOutput(BaseModel):
    original_input: str
    display_name: str
    normalized_key: str


class RequirementWarning(BaseModel):
    code: Literal["REQUIRED_AND_PREFERRED_AVOID"] = "REQUIRED_AND_PREFERRED_AVOID"
    item_id: int
    display_name: str
    normalized_key: str
    message: str


class RequirementsOutput(BaseModel):
    must_use: list[PantryItemOutput]
    prefer_to_avoid: list[PreferenceOutput]
    excluded: list[PreferenceOutput] = Field(default_factory=list)
    warnings: list[RequirementWarning]
    check_scope: Literal["reviewed_name_overlap_only"] = "reviewed_name_overlap_only"
    recipe_generated: Literal[False] = False
