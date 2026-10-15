"""Domain methods guard invariants; mapped attributes remain an escape hatch."""

from decimal import Decimal
from uuid import UUID

from pydantic import Field
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dddorm import AggregateRoot, Entity, ValueObject


class Money(ValueObject):
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Order(AggregateRoot):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'finalised')", name="order_status"),
    )

    _status: Mapped[str] = mapped_column("status", String(16), nullable=False)
    _currency: Mapped[str] = mapped_column("currency", String(3), nullable=False)
    # Eager loading prevents accidental async lazy IO during domain methods.
    _lines: Mapped[list["OrderLine"]] = relationship(
        cascade="save-update, merge, delete, delete-orphan",
        lazy="selectin",
        order_by="OrderLine.id",
    )

    def __init__(self, currency: str = "GBP") -> None:
        validated = Money(amount=Decimal("0"), currency=currency)
        super().__init__(_status="draft", _currency=validated.currency)

    @property
    def status(self) -> str:
        return self._status

    @property
    def currency(self) -> str:
        return self._currency

    @property
    def lines(self) -> tuple["OrderLine", ...]:
        return tuple(self._lines)

    @property
    def total(self) -> Money:
        amount = sum(
            (line.unit_price.amount * line.quantity for line in self._lines),
            Decimal("0"),
        )
        return Money(amount=amount, currency=self.currency)

    def _require_draft(self) -> None:
        if self._status != "draft":
            raise ValueError("A finalised order cannot be modified")

    def add_line(self, product_code: str, quantity: int, unit_price: Money) -> "OrderLine":
        self._require_draft()
        if not product_code.strip() or len(product_code) > 100:
            raise ValueError("Product code must contain 1–100 characters")
        self._validate_quantity(quantity)
        if unit_price.currency != self.currency:
            raise ValueError("Every line must use the order's currency")
        # Validate the resulting aggregate total before changing any state.
        Money(amount=self.total.amount + unit_price.amount * quantity, currency=self.currency)
        self._mark_changed()
        line = OrderLine(
            _product_code=product_code,
            _quantity=quantity,
            _amount=unit_price.amount,
            _currency=unit_price.currency,
        )
        self._lines.append(line)
        return line

    def change_quantity(self, line_id: UUID, quantity: int) -> None:
        self._require_draft()
        self._validate_quantity(quantity)
        line = self._find_line(line_id)
        Money(
            amount=self.total.amount + line.unit_price.amount * (quantity - line.quantity),
            currency=self.currency,
        )
        # Even assigning the same quantity asserts the loaded aggregate version.
        self._mark_changed()
        line._quantity = quantity

    def remove_line(self, line_id: UUID) -> None:
        self._require_draft()
        line = self._find_line(line_id)
        self._mark_changed()
        self._lines.remove(line)

    def finalise(self) -> None:
        self._require_draft()
        if not self._lines:
            raise ValueError("An empty order cannot be finalised")
        self._mark_changed()
        self._status = "finalised"

    def _find_line(self, line_id: UUID) -> "OrderLine":
        for line in self._lines:
            if line.id == line_id:
                return line
        raise KeyError(line_id)

    @staticmethod
    def _validate_quantity(quantity: int) -> None:
        if type(quantity) is not int or not 1 <= quantity <= 2_147_483_647:
            raise ValueError("Quantity must be a positive 32-bit integer")


class OrderLine(Entity):
    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="order_line_positive_quantity"),
        CheckConstraint("unit_amount >= 0", name="order_line_nonnegative_price"),
    )

    _order_id: Mapped[UUID] = mapped_column(
        "order_id", ForeignKey("orders.id"), nullable=False, index=True
    )
    _product_code: Mapped[str] = mapped_column("product_code", String(100), nullable=False)
    _quantity: Mapped[int] = mapped_column("quantity", Integer, nullable=False)
    _amount: Mapped[Decimal] = mapped_column("unit_amount", Numeric(18, 2), nullable=False)
    _currency: Mapped[str] = mapped_column("currency", String(3), nullable=False)

    @property
    def product_code(self) -> str:
        return self._product_code

    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def unit_price(self) -> Money:
        # Immutable values are reconstructed from scalar columns, not mapped
        # as entities. Replacing money would be an explicit Order operation.
        return Money(amount=self._amount, currency=self._currency)
