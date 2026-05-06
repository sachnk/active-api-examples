import logging
import math
import random
import time
import pandas as pd

from dataclasses import dataclass
from typing import List
from massive.websocket.models import EquityQuote
from common import BaseEngine
from common.models import Order, EngineConfig

@dataclass
class Stats:
    submitted_at: int
    acked_at: int
    order_id: str

class Engine(BaseEngine):
    def __init__(self, config: EngineConfig, min_edge: float, num_levels: int):
        super().__init__(config)
        self.min_edge = min_edge
        self.num_levels = num_levels
        self.theo: float = math.nan
        self.dirty = False
        self.stats: List[Stats] = []

        if self.min_edge < 0:
            raise ValueError("min_edge must be greater than 0")

        if self.min_edge < self.config.min_tick:
            raise ValueError("min_tick must be greater than min_edge")

    def on_order_update(self, timestamp: int, order: Order) -> None:
        super().on_order_update(timestamp, order)
        stats = list(filter(lambda x: x.order_id == order.id, self.stats))
        if len(stats) > 0:
            stats[0].acked_at = timestamp

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

    def eval(self) -> bool:
        if not self.ready:
            return False

        logging.info("---- begin eval: theo = %.2f", self.theo)

        if math.isnan(self.theo):
            logging.info("no theo; cancelling all orders")
            self.cancel_all_orders()
            return True

        open_buys: List[float] = []
        open_sells: List[float] = []
        # cancel orders with insufficient edge
        for order in self.open_orders.values():
            price = float(order.limit_price)
            open_buys.append(price) if order.side == "BUY" else open_sells.append(price)
            edge = (
                math.fabs(self.theo - price)
                if order.side == "BUY"
                else math.fabs(price - self.theo)
            )
            if edge < self.min_edge:
                logging.info(
                    "%s @ %.2f, edge=%.3f, cancelling...", order.side, price, edge
                )
                self.cancel_order(order)
            else:
                logging.info("%s @ %.2f, edge=%.3f", order.side, price, edge)

        open_buys.sort()
        open_sells.sort()

        # fill in missing levels
        price = (
            open_buys[0] - self.config.min_tick
            if len(open_buys) > 0
            else self.theo - self.min_edge
        )
        for i in range(self.num_levels - len(open_buys)):
            if price < self.config.min_tick:
                break
            size = random.randint(self.config.min_size, self.config.max_size)
            self.send("BUY", size, price)
            price -= self.config.min_tick

        price = (
            open_sells[-1] - self.config.min_tick
            if len(open_sells) > 0
            else self.theo + self.min_edge
        )
        for i in range(self.num_levels - len(open_sells)):
            size = random.randint(self.config.min_size, self.config.max_size)
            self.send("SELL", size, price)
            price += self.config.min_tick

        logging.info("---- end eval: theo = %.2f", self.theo)
        return True
    
    def send(self, side: str, quantity: int, price: float):
        timestamp = int(time.time() * 1000)
        order_id = self.submit_order(side, quantity, self.to_tick(price), "DAY")
        self.stats.append(Stats(submitted_at=timestamp, acked_at=0, order_id=order_id))

    def dump_stats(self):
        df = pd.DataFrame([x.acked_at - x.submitted_at for x in self.stats], columns=["latency"])
        logging.info("latency data:\n%s", df.describe())
        logging.info("latency percentiles:\n%s", df["latency"].quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]))


