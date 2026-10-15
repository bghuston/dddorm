"""Task-owned sessions with explicit, independently scoped transactions."""

import asyncio
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import TracebackType
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

ExitAction = Literal["commit", "flush", "rollback"]


@dataclass(frozen=True)
class _Binding:
    session: AsyncSession
    task: asyncio.Task[object]


_active: ContextVar[_Binding | None] = ContextVar("dddorm_active_session", default=None)


def current_session() -> AsyncSession:
    """Return this task's session, refusing a copied child-task context."""
    binding = _active.get()
    if binding is None:
        raise RuntimeError("No active UnitOfWork")
    if binding.task is not asyncio.current_task():
        raise RuntimeError("A UnitOfWork session cannot be inherited by another task")
    return binding.session


class UnitOfWork:
    """One session per scope; nested scopes are rejected.

    Default exit is rollback: persistence requires commit() or on_exit='commit'.
    on_exit='flush' sends SQL for validation, then rolls it back; flush is never
    durable. A commit ends a transaction, not the session scope. Subsequent work
    starts a new transaction through SQLAlchemy autobegin.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        on_exit: ExitAction = "rollback",
    ) -> None:
        if on_exit not in {"commit", "flush", "rollback"}:
            raise ValueError("on_exit must be commit, flush, or rollback")
        self._factory = session_factory
        self._on_exit = on_exit
        self._session: AsyncSession | None = None
        self._token: Token[_Binding | None] | None = None

    async def __aenter__(self) -> "UnitOfWork":
        if self._session is not None:
            raise RuntimeError("This UnitOfWork is already active")
        binding = _active.get()
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("UnitOfWork requires an asyncio task")
        if binding is not None and binding.task is task:
            raise RuntimeError("Nested Units of Work are not supported")
        # Child tasks may start their own independent scope, replacing the copied
        # binding. Factories must return a fresh session on every call.
        session = self._factory()
        if binding is not None and session is binding.session:
            raise RuntimeError("The factory returned the inherited session; a fresh session is required")
        self._session = session
        self._token = _active.set(_Binding(session, task))
        return self

    @property
    def session(self) -> AsyncSession:
        if self._session is None or current_session() is not self._session:
            raise RuntimeError("This UnitOfWork does not own the active session")
        return self._session

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self.session  # Verify ownership before doing any cleanup.
        token = self._token
        assert token is not None
        try:
            try:
                if exc_type is not None:
                    await session.rollback()
                elif self._on_exit == "commit":
                    await session.commit()
                else:
                    if self._on_exit == "flush":
                        await session.flush()
                    await session.rollback()
            except BaseException:
                await session.rollback()
                raise
        finally:
            try:
                await session.close()
            finally:
                _active.reset(token)
                self._session = None
                self._token = None
