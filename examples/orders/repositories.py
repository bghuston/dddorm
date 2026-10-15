from uuid import UUID

from sqlalchemy import select

from dddorm import Repository

from .models import Order


class OrderRepository(Repository[Order]):
    @property
    def model(self) -> type[Order]:
        return Order

    async def drafts(self) -> list[Order]:
        """A domain-specific query; lines are loaded by the relationship strategy."""
        result = await self.session.scalars(
            select(Order).where(Order._status == "draft").order_by(Order.id)
        )
        return list(result)

    async def require(self, id: UUID) -> Order:
        order = await self.get_by_id(id)
        if order is None:
            raise LookupError(f"Order {id} was not found")
        return order
