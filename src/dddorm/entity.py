"""SQLAlchemy persistence identity, independent of entity attribute values."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Entity(DeclarativeBase):
    """Abstract mapped base. IDs are assigned before persistence.

    Equality uses concrete type and ID. Entities are deliberately unhashable:
    SQLAlchemy still permits primary-key assignment, which would invalidate sets.
    Application code must treat IDs as immutable.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid4())
        for key, value in kwargs.items():
            if not hasattr(type(self), key):
                raise TypeError(f"{key!r} is not a mapped attribute of {type(self).__name__}")
            setattr(self, key, value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        if type(self) is not type(other):
            return False
        if self.id is None or other.id is None:
            return self is other
        return self.id == other.id

    __hash__ = None  # type: ignore[assignment]
