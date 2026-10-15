"""Repositories load whole consistency boundaries and never commit."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .aggregate import AggregateRoot
from .unit_of_work import current_session

T = TypeVar("T", bound=AggregateRoot)


class Repository(ABC, Generic[T]):
    def __init__(self, session: AsyncSession | None = None) -> None:
        # Explicit sessions belong to the caller, including their concurrency rules.
        self._session = session
        if not issubclass(self.model, AggregateRoot):
            raise TypeError("Repositories must target aggregate roots")

    @property
    @abstractmethod
    def model(self) -> type[T]:
        """The concrete mapped aggregate type."""
        raise NotImplementedError

    @property
    def session(self) -> AsyncSession:
        return self._session if self._session is not None else current_session()

    async def get_by_id(self, id: UUID) -> T | None:
        return await self.session.get(self.model, id)

    def add(self, aggregate: T) -> None:
        if not isinstance(aggregate, self.model):
            raise TypeError("Unexpected aggregate type")
        self.session.add(aggregate)
