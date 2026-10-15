"""Illustrations for reading; no entry point or automatic database activity.

Callers supply an async_sessionmaker configured with expire_on_commit=False
and a schema created separately. No sessions or transactions escape a service.
"""

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dddorm import StaleDataError, UnitOfWork

from .models import Money, Order
from .repositories import OrderRepository

SessionFactory = Callable[[], AsyncSession]


async def create_order(session_factory: SessionFactory) -> UUID:
    async with UnitOfWork(session_factory, on_exit="commit"):
        order = Order(currency="GBP")
        order.add_line("BOOK", 2, Money(amount=Decimal("12.50"), currency="GBP"))
        OrderRepository().add(order)
        order_id = order.id
    return order_id


async def finalise_order(session_factory: SessionFactory, order_id: UUID) -> None:
    async with UnitOfWork(session_factory, on_exit="commit"):
        order = await OrderRepository().require(order_id)
        order.finalise()


async def change_quantity(
    session_factory: SessionFactory, order_id: UUID, line_id: UUID, quantity: int
) -> None:
    async with UnitOfWork(session_factory, on_exit="commit"):
        order = await OrderRepository().require(order_id)
        order.change_quantity(line_id, quantity)


async def illustrate_conflict(session_factory: SessionFactory) -> str:
    """Two independent sessions read the same draft and try to finalise it.

    This low-level illustration intentionally exposes sessions to explain the
    mechanism. Services above use repositories and UoW. A DB that allows both
    reads and the first commit is assumed (e.g. READ COMMITTED PostgreSQL).
    Stronger isolation may report a database serialization error instead.
    """
    order_id = await create_order(session_factory)
    async with session_factory() as first, session_factory() as second:
        first_order = await OrderRepository(first).require(order_id)
        second_order = await OrderRepository(second).require(order_id)
        first_order.finalise()
        second_order.finalise()
        await first.commit()
        try:
            # UPDATE orders ... WHERE id = :id AND version = :old_version
            # affects zero rows, so SQLAlchemy raises StaleDataError.
            await second.commit()
        except StaleDataError:
            await second.rollback()
            return "The stale aggregate was rejected; reload and reconsider the command."
    raise RuntimeError("Expected the second writer to encounter a version conflict")
