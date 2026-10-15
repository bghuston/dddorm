"""Aggregate roots and SQLAlchemy's per-row optimistic version check."""

from typing import Any

from sqlalchemy import Integer, inspect
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from .entity import Entity


class AggregateRoot(Entity):
    __abstract__ = True

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}

    def _mark_changed(self) -> None:
        """Include child-only changes in the root's optimistic write check.

        Pending/transient roots receive version 1 on INSERT. Existing roots
        explicitly advance their version, forcing an UPDATE even if a domain
        operation only changes children or writes the same scalar value.
        Call this after validation in every aggregate mutation method.
        """
        state = inspect(self)
        if state.detached:
            raise RuntimeError("Reload the aggregate in an active session before mutation")
        if state.persistent:
            self.version += 1
