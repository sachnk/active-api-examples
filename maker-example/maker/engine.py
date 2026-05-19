import logging
import math
import random
import pandas as pd

from typing import List, Tuple
from massive.websocket.models import EquityQuote
from common import BaseEngine
from common.models import Order, EngineConfig

# (price, qty, edge, status) where status is "kept", "cancelled", or "submitted"
BookRow = Tuple[float, int, float, str]


class Engine(BaseEngine):
    def __init__(self, config: EngineConfig, side: str, min_edge: float, num_levels: int):
        super().__init__(config)
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        self.side = side
        self.min_edge = min_edge
        self.num_levels = num_levels
        self.theo: float = math.nan
        self.dirty = False

        if self.min_edge < 0:
            raise ValueError("min_edge must be greater than 0")

        if self.min_edge < self.config.min_tick:
            raise ValueError("min_tick must be greater than min_edge")

    def on_order_update(self, timestamp: int, order: Order) -> None:
        super().on_order_update(timestamp, order)
        self.dirty = True

    def on_quote_update(self, quote: EquityQuote) -> None:
        super().on_quote_update(quote)

        theo = (quote.bid_price + quote.ask_price) / 2.0
        if math.fabs(theo - self.theo) < 0.01:
            return

        self.theo = theo
        self.dirty = True

    def on_timer(self) -> None:
        if not self.dirty:
            return

        if self.eval():
            self.dirty = False

    def _edge(self, price: float) -> float:
        return (
            math.fabs(self.theo - price)
            if self.side == "BUY"
            else math.fabs(price - self.theo)
        )

    def eval(self) -> bool:
        if not self.ready:
            return False

        if math.isnan(self.theo):
            logging.info("%s %s: no theo; cancelling all orders", self.config.symbol, self.side)
            self.cancel_all_orders()
            return True

        rows: List[BookRow] = []

        # cancel orders with insufficient edge; collect survivors. Snapshot
        # the values: cancel_order() may pop from self.open_orders on a 4xx,
        # which would otherwise mutate the dict mid-iteration.
        survivor_prices: List[float] = []
        for order in list(self.open_orders.values()):
            price = float(order.limit_price)
            qty = int(order.leaves_quantity)
            edge = self._edge(price)
            if edge < self.min_edge:
                self.cancel_order(order)
                rows.append((price, qty, edge, "cancelled"))
            else:
                rows.append((price, qty, edge, "kept"))
                survivor_prices.append(price)

        survivor_prices.sort()

        # fill in missing levels, walking away from theo by min_tick
        if self.side == "BUY":
            price = (
                survivor_prices[0] - self.config.min_tick
                if survivor_prices
                else self.theo - self.min_edge
            )
            step = -self.config.min_tick
        else:
            price = (
                survivor_prices[-1] - self.config.min_tick
                if survivor_prices
                else self.theo + self.min_edge
            )
            step = self.config.min_tick

        for _ in range(self.num_levels - len(survivor_prices)):
            if price < self.config.min_tick:
                break
            size = random.randint(self.config.min_size, self.config.max_size)
            self.submit_order(self.side, size, self.to_tick(price), "DAY")
            rows.append((price, size, self._edge(price), "submitted"))
            price += step

        # Suppress the book panel when this eval was a no-op (every row "kept",
        # i.e. no cancels and no new submits).
        if any(status != "kept" for _, _, _, status in rows):
            self._render_book(rows)
        return True

    def _render_book(self, rows: List[BookRow]) -> None:
        """Print a price-sorted ladder of our orders with theo/bbo markers."""
        quote = self.quotes.get(self.config.symbol)

        # Build the ladder: each entry is (price, kind, payload).
        ladder = [(p, "order", (q, e, s)) for p, q, e, s in rows]
        ladder.append((self.theo, "marker", "theo"))
        if quote:
            ladder.append((float(quote.bid_price), "marker", "bid"))
            ladder.append((float(quote.ask_price), "marker", "ask"))
        ladder.sort(key=lambda x: x[0], reverse=True)

        bbo = (
            f"{float(quote.bid_price):.2f} / {float(quote.ask_price):.2f}"
            if quote else "n/a"
        )
        header = (
            f"{self.config.symbol} {self.side}  "
            f"pos={self.position}  theo={self.theo:.2f}  bbo={bbo}"
        )

        lines = ["", f"  ╭─ {header}", "  │"]
        for price, kind, payload in ladder:
            if kind == "marker":
                lines.append(f"  │   {price:>8.2f}   ··· {payload} ···")
            else:
                qty, edge, status = payload
                sigil = {"kept": " ", "cancelled": "✗", "submitted": "+"}[status]
                tag = "" if status == "kept" else f"  {status}"
                lines.append(
                    f"  │ {sigil} {price:>8.2f}   {qty:>5}    e={edge:.2f}{tag}"
                )
        lines.append("  ╰─")

        logging.info("\n".join(lines))

    def dump_stats(self):
        for label, samples in (
            ("submit", self.submit_latencies),
            ("cancel", self.cancel_latencies),
        ):
            if not samples:
                logging.info("%s %s latency: no samples", self.config.symbol, label)
                continue
            df = pd.DataFrame(samples, columns=["latency_ms"])
            logging.info(
                "%s %s latency (ms) — describe:\n%s",
                self.config.symbol, label, df.describe(),
            )
            logging.info(
                "%s %s latency (ms) — percentiles:\n%s",
                self.config.symbol, label,
                df["latency_ms"].quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]),
            )
