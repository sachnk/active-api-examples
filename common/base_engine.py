import logging
import time
import requests
from typing import Dict, List
from massive.websocket.models import EquityQuote, EquityAgg
from .models import Order, Trade, Position, EngineConfig


class BaseEngine:
    def __init__(self, config: EngineConfig):
        self.config = config
        self.position: int = 0
        self.open_orders: Dict[str, Order] = {}
        self.submitted_orders: List[str] = []
        self.ready = False
        self.num_rejects: int = 0
        self.quotes: Dict[str, EquityQuote] = {}
        self.agg_sec: Dict[str, EquityAgg] = {}
        self.agg_min: Dict[str, EquityAgg] = {}
        # Per-request roundtrip latencies (ms) for completed HTTP responses.
        self.submit_latencies: List[float] = []
        self.cancel_latencies: List[float] = []
        self.config.validate()

    # invoked when the first poll cycle completes
    def on_ready(self):
        self.cancel_all_orders()
        self.ready = True
        logging.info(
            "%s engine ready, position = %d", self.config.symbol, self.position
        )

    # invoked when an order state updates
    def on_order_update(self, timestamp: int, order: Order) -> None:
        if order.id not in self.submitted_orders:
            return

        if order.symbol != self.config.symbol:
            return

        if order.status == "REJECTED":
            logging.warn("Order %s rejected: %s", order.id, order.details)
            self.num_rejects += 1
            if self.num_rejects >= self.config.max_rejects:
                raise RuntimeError("Too many rejects")

        if order.is_open():
            self.open_orders[order.id] = order
        else:
            self.open_orders.pop(order.id, None)

    # invoked when a fill is detected against an open order
    def on_trade_notice(self, timestamp: int, trade: Trade) -> None:
        if trade.symbol != self.config.symbol:
            return

        logging.info(
            "%s trade: %s %s @ %s",
            self.config.symbol,
            trade.side,
            trade.quantity,
            trade.price,
        )

    # invoked when a position update is detected
    def on_position_update(self, timestamp: int, position: Position) -> None:
        if position.symbol != self.config.symbol:
            return

        self.position = int(float(position.quantity))
        logging.info("%s position: %s", self.config.symbol, self.position)

    # invoked when a quote update occurs from massive
    def on_quote_update(self, quote: EquityQuote) -> None:
        self.quotes[quote.symbol] = quote

    # invoked when a second aggregate update occurs from massive
    def on_agg_sec_update(self, agg: EquityAgg) -> None:
        self.agg_sec[agg.symbol] = agg

    # invoked when a minute aggregate update occurs from massive
    def on_agg_min_update(self, agg: EquityAgg) -> None:
        self.agg_min[agg.symbol] = agg

    def on_timer(self) -> None:
        pass

    def submit_order(self, side: str, quantity: int, price: str, tif: str) -> str:
        logging.info("Submitting order: %s %d @ %s...", side, quantity, price)

        if self.position > 0:
            if side == "BUY":
                if self.position + quantity > self.config.max_position:
                    logging.info("Cannot submit order; max position will breach")
                    return
            else:
                quantity = min(quantity, self.position)
        elif self.position < 0:
            if side == "SELL":
                if self.position - quantity < -self.config.max_position:
                    logging.info("Cannot submit order; max position will breach")
                    return
            else:
                quantity = min(quantity, -self.position)

        url = f"{self.config.url}/accounts/{self.config.account}/orders"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        t_start = time.perf_counter()
        response = requests.post(
            url,
            headers=headers,
            json=[
                {
                    "instrument_type": "COMMON_STOCK",
                    "symbol": self.config.symbol,
                    "side": side,
                    "quantity": str(quantity),
                    "limit_price": price,
                    "order_type": "LIMIT",
                    "time_in_force": tif,
                    "strategy": {"type": "SOR"},
                }
            ],
        )
        self.submit_latencies.append((time.perf_counter() - t_start) * 1000)
        if not response.ok:
            raise RuntimeError(
                f"Failed submitting order: {response.status_code}, {response.text}"
            )

        order_id = response.json()["data"][0]["id"]
        self.submitted_orders.append(order_id)
        logging.info("Submitted order-id %s", order_id)

        return order_id

    def cancel_order(self, order: Order) -> None:
        url = f"{self.config.url}/accounts/{self.config.account}/orders/{order.id}"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        t_start = time.perf_counter()
        response = requests.delete(url, headers=headers)
        self.cancel_latencies.append((time.perf_counter() - t_start) * 1000)
        # 4xx means the order isn't in a cancellable state (404 = unknown id,
        # 409/422 = already filled/cancelled). Treat as a benign race: drop our
        # local view of the order and move on. The next poll will reconcile.
        if 400 <= response.status_code < 500:
            logging.warning(
                "Cancel of %s returned %d: %s",
                order.id, response.status_code, response.text,
            )
            self.open_orders.pop(order.id, None)
            return
        if not response.ok:
            raise RuntimeError(
                f"Failed cancelling order: {response.status_code}, {response.text}"
            )

        logging.info("Cancelled order: %s", order.id)

    def cancel_all_orders(self) -> None:
        url = f"{self.config.url}/accounts/{self.config.account}/orders"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        t_start = time.perf_counter()
        response = requests.delete(url, headers=headers)
        self.cancel_latencies.append((time.perf_counter() - t_start) * 1000)
        if 400 <= response.status_code < 500:
            logging.info(
                "Cancel-all returned %d: %s", response.status_code, response.text
            )
            return
        if not response.ok:
            raise RuntimeError(
                f"Failed cancelling all orders: {response.status_code}, {response.text}"
            )

        logging.info("Cancelled all orders")

    def to_tick(self, price: float) -> str:
        val = round(price / self.config.min_tick) * self.config.min_tick
        return "{:.2f}".format(val)
