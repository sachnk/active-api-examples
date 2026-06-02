import logging
import math
from typing import Optional

from massive.websocket.models import EquityQuote
from common import BaseEngine
from common.models import Order, EngineConfig


TICK = 0.01  # treat $0.01 as the unit "tick" for the BBO offset, per spec.


class Engine(BaseEngine):
    """Single-order, BBO-offset option quoter.

    Maintains at most one open order priced ``bbo_offset_ticks`` ticks worse
    than the current BBO for the configured side (lower than best bid for
    BUY, higher than best ask for SELL). On every quote update, if our open
    order's price no longer matches the new target, it gets cancelled. The
    next eval will resubmit at the new target.
    """

    def __init__(self, config: EngineConfig, side: str, bbo_offset_ticks: int = 2):
        super().__init__(config)
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if bbo_offset_ticks < 0:
            raise ValueError("bbo_offset_ticks must be >= 0")
        self.side = side
        self.bbo_offset = bbo_offset_ticks * TICK
        self.target_price: Optional[float] = None
        self.dirty = False

    def _target_from_quote(self, quote: EquityQuote) -> Optional[float]:
        ref = quote.bid_price if self.side == "BUY" else quote.ask_price
        if ref is None or ref <= 0:
            return None
        target = float(ref) - self.bbo_offset if self.side == "BUY" else float(ref) + self.bbo_offset
        if target <= 0:
            return None
        return target

    def on_quote_update(self, quote: EquityQuote) -> None:
        super().on_quote_update(quote)
        new_target = self._target_from_quote(quote)
        if new_target is None:
            return
        if self.target_price is None or math.fabs(new_target - self.target_price) >= self.config.min_tick / 2:
            self.target_price = new_target
            self.dirty = True

    def on_order_update(self, timestamp: int, order: Order) -> None:
        super().on_order_update(timestamp, order)
        self.dirty = True

    def on_timer(self) -> None:
        if not self.dirty:
            return
        if self.eval():
            self.dirty = False

    def eval(self) -> bool:
        if not self.ready:
            return False
        if self.target_price is None:
            return True  # no quote yet — nothing to do, clear dirty

        target_str = self.to_tick(self.target_price)

        # Cancel any open order whose price doesn't match the target.
        # Snapshot the values because cancel_order may pop on a 4xx.
        kept: Optional[Order] = None
        for order in list(self.open_orders.values()):
            if order.limit_price == target_str:
                kept = order
            else:
                logging.info(
                    "%s %s @ %s != target %s, cancelling",
                    self.config.symbol, order.side, order.limit_price, target_str,
                )
                self.cancel_order(order)

        if kept is not None:
            # Already at target; nothing else to do.
            return True

        # No open order at target — submit one at min_size (single order, no layering).
        size = self.config.min_size
        if size < 1:
            return True
        logging.info(
            "%s %s @ %s (qty=%d) — matching BBO",
            self.config.symbol, self.side, target_str, size,
        )
        self.submit_order(self.side, size, target_str, "DAY")
        return True

    def dump_stats(self):
        # Latency stats are tracked on the base engine; keep a minimal summary.
        n_submit = len(self.submit_latencies)
        n_cancel = len(self.cancel_latencies)
        logging.info(
            "%s %s: %d submits, %d cancels",
            self.config.symbol, self.side, n_submit, n_cancel,
        )
