"""
Fare breakdown: base fare vs taxes vs user-development fee (UDF) vs convenience fee.

The problem statement asks for these to be separated. Not every source exposes
all of them, so unknown parts are None and `known_total()` says what we can
vouch for. This is a standalone value object; the scraper's FareRecord is not
changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_TOLERANCE_INR = 1.0


@dataclass(frozen=True)
class FareBreakdown:
    total: float
    base_fare: Optional[float] = None
    taxes: Optional[float] = None
    user_development_fee: Optional[float] = None
    convenience_fee: Optional[float] = None
    other_charges: Optional[float] = None

    def __post_init__(self) -> None:
        if self.total is None or self.total <= 0:
            raise ValueError("total must be positive")
        parts = self._parts()
        if any(p < 0 for p in parts):
            raise ValueError("fare components cannot be negative")
        if self.is_complete() and abs(sum(parts) - self.total) > _TOLERANCE_INR:
            raise ValueError(f"components sum to {sum(parts):.2f}, total is {self.total:.2f}")
        if sum(parts) > self.total + _TOLERANCE_INR:
            raise ValueError("components exceed total")

    def _parts(self) -> "list[float]":
        return [p for p in (self.base_fare, self.taxes, self.user_development_fee,
                            self.convenience_fee, self.other_charges) if p is not None]

    def is_complete(self) -> bool:
        return all(p is not None for p in (self.base_fare, self.taxes, self.user_development_fee, self.convenience_fee))

    def price_for(self, basis: str = "total") -> Optional[float]:
        """Price to feed an index. basis: 'total' | 'ex_convenience' | 'base'."""
        if basis == "total":
            return self.total
        if basis == "ex_convenience":
            return self.total - self.convenience_fee if self.convenience_fee is not None else None
        if basis == "base":
            return self.base_fare
        raise ValueError(f"unknown basis {basis!r}")
