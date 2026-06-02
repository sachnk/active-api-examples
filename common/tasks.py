import asyncio
import logging
import time

import requests
from massive import WebSocketClient
from massive.websocket.models import WebSocketMessage, EquityQuote, EquityAgg
from massive.websocket.models.common import Feed, Market
from typing import Dict, List, Optional

from .models import Order, Trade, Position
from .base_engine import BaseEngine


def _normalize_option_symbol(s: str) -> str:
    """Strip spaces and an optional 'O:' prefix from an option symbol.

    Clear Street returns OSI with spaces (``AAPL  260320C00180000``); Massive
    uses no spaces with an ``O:`` prefix on the wire (``O:AAPL260320C00180000``).
    We normalize both to spaceless-no-prefix so they can be matched."""
    s = s.replace(" ", "")
    if s.startswith("O:"):
        s = s[2:]
    return s


async def massive_processor(
    sym_to_engine: Dict[str, BaseEngine], msgs: List[WebSocketMessage]
):
    for msg in msgs:
        engine = sym_to_engine.get(msg.symbol) or sym_to_engine.get(
            _normalize_option_symbol(msg.symbol)
        )
        if engine is None:
            continue
        if msg.event_type == "Q":
            msg: EquityQuote = msg
            engine.on_quote_update(msg)
        elif msg.event_type == "A":
            msg: EquityAgg = msg
            engine.on_agg_sec_update(msg)
        elif msg.event_type == "AM":
            msg: EquityAgg = msg
            engine.on_agg_min_update(msg)


async def ws_massive_task(
    engines: List[BaseEngine],
    api_key: str,
    market: Market = Market.Stocks,
):
    """Subscribe to Massive quotes/aggregates for each engine's symbol.

    For ``Market.Options`` the engine's ``config.symbol`` is expected to be the
    OSI form *with* spaces (the order-submission shape); the WS subscription
    string is built by stripping spaces and prepending ``O:``."""
    if market == Market.Options:
        sub_symbols = {
            "O:" + e.config.symbol.replace(" ", ""): e for e in engines
        }
        # Dispatcher key: spaceless-no-prefix; tolerate either form via _normalize_.
        sym_to_engine = {
            e.config.symbol.replace(" ", ""): e for e in engines
        }
    else:
        sub_symbols = {e.config.symbol: e for e in engines}
        sym_to_engine = {e.config.symbol: e for e in engines}

    wire_symbols = list(sub_symbols.keys())
    subscriptions = (
        [f"Q.{s}" for s in wire_symbols]
        + [f"A.{s}" for s in wire_symbols]
        + [f"AM.{s}" for s in wire_symbols]
    )

    ws = WebSocketClient(
        api_key=api_key,
        feed=Feed.RealTime,
        market=market,
        subscriptions=subscriptions,
        verbose=True,
    )
    await ws.connect(processor=lambda msgs: massive_processor(sym_to_engine, msgs))


def _fetch_orders(url: str, api_key: str, account: str, symbol: str) -> List[Order]:
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(
        f"{url}/accounts/{account}/orders",
        headers=headers,
        params={"symbol": symbol, "page_size": 1000},
    )
    resp.raise_for_status()
    return [Order.from_api(o) for o in resp.json().get("data", [])]


def _fetch_position(url: str, api_key: str, account: str, symbol: str) -> Optional[Position]:
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(
        f"{url}/accounts/{account}/positions",
        headers=headers,
        params={"page_size": 1000},
    )
    resp.raise_for_status()
    for p in resp.json().get("data", []):
        if p.get("symbol") == symbol:
            return Position.from_api(p)
    return None


async def poll_clst_task(
    engine: BaseEngine,
    url: str,
    api_key: str,
    account: str,
    symbol: str,
    interval: float = 1.0,
):
    last_orders: Dict[str, Order] = {}
    last_position_qty: Optional[str] = None
    first_poll = True

    logging.info("polling %s every %.2fs for %s", url, interval, symbol)

    while True:
        try:
            orders = await asyncio.to_thread(_fetch_orders, url, api_key, account, symbol)
            timestamp = int(time.time() * 1000)

            for order in orders:
                prev = last_orders.get(order.id)
                changed = (
                    prev is None
                    or prev.status != order.status
                    or prev.filled_quantity != order.filled_quantity
                )
                if not changed:
                    continue

                prev_filled = float(prev.filled_quantity) if prev else 0.0
                curr_filled = float(order.filled_quantity)
                if curr_filled > prev_filled:
                    fill_qty = curr_filled - prev_filled
                    fill_price = order.average_fill_price or order.limit_price or "0"
                    engine.on_trade_notice(
                        timestamp,
                        Trade(
                            order_id=order.id,
                            symbol=order.symbol,
                            side=order.side,
                            quantity=str(int(fill_qty) if fill_qty.is_integer() else fill_qty),
                            price=fill_price,
                            created_at=order.updated_at,
                        ),
                    )

                engine.on_order_update(timestamp, order)
                last_orders[order.id] = order

            position = await asyncio.to_thread(_fetch_position, url, api_key, account, symbol)
            if position is None:
                position = Position(account_id=0, symbol=symbol, quantity="0")

            if last_position_qty != position.quantity:
                engine.on_position_update(timestamp, position)
                last_position_qty = position.quantity

            if first_poll:
                first_poll = False
                engine.on_ready()

        except requests.RequestException:
            logging.exception("clst poll failed")

        await asyncio.sleep(interval)


async def timer_task(engine: BaseEngine):
    while True:
        engine.on_timer()
        await asyncio.sleep(1)
