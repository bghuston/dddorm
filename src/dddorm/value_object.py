"""Validated, value-equal immutable domain data."""

from pydantic import BaseModel, ConfigDict


class ValueObject(BaseModel):
    """Subclasses must also choose immutable types for nested fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")
