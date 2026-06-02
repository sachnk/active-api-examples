from typing import List, Optional
from dataclasses import dataclass, fields


OPEN_STATUSES = {"PENDING_NEW", "NEW", "PARTIALLY_FILLED", "PENDING_CANCEL", "PENDING_REPLACE", "REPLACED"}
TERMINAL_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "DONE_FOR_DAY", "STOPPED"}


def _filter_kwargs(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class Order:
    id: str
    account_id: int
    symbol: str
    side: str
    status: str
    order_type: str
    time_in_force: str
    quantity: str
    filled_quantity: str
    leaves_quantity: str
    instrument_type: str
    created_at: str
    updated_at: str
    security_id: Optional[str] = None
    security_id_source: Optional[str] = None
    venue: Optional[str] = None
    client_order_id: Optional[str] = None
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    average_fill_price: Optional[str] = None
    details: Optional[List[str]] = None
    expires_at: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> "Order":
        return cls(**_filter_kwargs(cls, data))

    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


@dataclass
class Trade:
    order_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    created_at: str


@dataclass
class Position:
    account_id: int
    symbol: str
    quantity: str
    instrument_type: str = "COMMON_STOCK"
    security_id: Optional[str] = None
    security_id_source: Optional[str] = None
    position_type: Optional[str] = None
    available_quantity: Optional[str] = None
    market_value: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> "Position":
        return cls(**_filter_kwargs(cls, data))


@dataclass
class EngineConfig:
    url: str
    api_key: str
    account: str
    symbol: str
    max_position: int
    min_size: int
    max_size: int
    min_tick: float
    max_rejects: int
    instrument_type: str = "COMMON_STOCK"
    position_effect: Optional[str] = None

    def validate(self):
        if self.min_tick < 0:
            raise ValueError("min_tick must be greater than 0")
        if self.max_position < 0:
            raise ValueError("min_position must be greater than 0")
