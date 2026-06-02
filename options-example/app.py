import sys

sys.path.append("..")

import signal
import argparse
import asyncio
import logging
from typing import List

import requests
from massive.websocket.models.common import Market

from options.engine import Engine
from options.contracts import fetch_contracts, filter_strikes, Contract
from common.models import EngineConfig
from common import add_common_args, ws_massive_task, poll_clst_task, timer_task

engines: list[Engine] = []


def signal_handler(sig, frame):
    for engine in engines:
        engine.cancel_all_orders()
    logging.info("Dumping stats...")
    for engine in engines:
        engine.dump_stats()
    sys.exit(0)


def _flatten_positions(args, symbols: List[str]) -> None:
    """Send market-close orders for any non-zero positions on these option symbols.

    Fired once at startup so the quoter begins from a flat state on each
    contract it cares about. Fire-and-forget — the poll task will reconcile
    once the closes fill. We log but don't raise on per-symbol failures so
    that one bad contract doesn't block the whole startup.
    """
    headers = {"Authorization": f"Bearer {args.api_key}"}
    try:
        resp = requests.get(
            f"{args.url}/accounts/{args.account}/positions",
            headers=headers,
            params={"page_size": 1000},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logging.exception("startup position fetch failed; skipping flatten")
        return

    target = set(symbols)
    closed = 0
    for p in resp.json().get("data", []):
        symbol = p.get("symbol")
        if symbol not in target:
            continue
        try:
            qty = int(float(p.get("quantity", 0)))
        except (TypeError, ValueError):
            continue
        if qty == 0:
            continue
        side = "SELL" if qty > 0 else "BUY"
        abs_qty = abs(qty)
        logging.info(
            "flattening %s: pos=%d -> %s MARKET x%d (CLOSE)",
            symbol, qty, side, abs_qty,
        )
        body = {
            "instrument_type": "OPTION",
            "symbol": symbol,
            "side": side,
            "quantity": str(abs_qty),
            "order_type": "MARKET",
            "time_in_force": "DAY",
            "strategy": {"type": "SOR"},
            "position_effect": "CLOSE",
        }
        try:
            close_resp = requests.post(
                f"{args.url}/accounts/{args.account}/orders",
                headers=headers,
                json=[body],
                timeout=15,
            )
        except requests.RequestException:
            logging.exception("flatten POST failed for %s", symbol)
            continue
        if not close_resp.ok:
            logging.warning(
                "flatten rejected for %s (%d): %s",
                symbol, close_resp.status_code, close_resp.text,
            )
            continue
        closed += 1

    if closed:
        logging.info("submitted %d flattening order(s)", closed)
    else:
        logging.info("no non-zero option positions to flatten")


def _build_engine(args, contract: Contract) -> Engine:
    side = "BUY" if contract.contract_type == "CALL" else "SELL"
    config = EngineConfig(
        url=args.url,
        api_key=args.api_key,
        account=args.account,
        symbol=contract.symbol,
        max_position=args.max_position,
        min_tick=args.min_tick,
        min_size=args.min_size,
        max_size=args.max_size,
        max_rejects=4,
        instrument_type="OPTION",
        position_effect="OPEN",
    )
    return Engine(config=config, side=side, bbo_offset_ticks=args.bbo_offset_ticks)


async def main(args):
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )

    logging.info(
        "fetching option contracts: underlier=%s expiry=%s strikes=[%.2f, %.2f]",
        args.underlier, args.expiry, args.min_strike, args.max_strike,
    )
    all_contracts = fetch_contracts(
        url=args.url,
        api_key=args.api_key,
        underlier=args.underlier,
        expiry=args.expiry,
    )
    contracts = filter_strikes(all_contracts, args.min_strike, args.max_strike)
    if not contracts:
        logging.error("no contracts found in the requested range; exiting")
        sys.exit(1)

    for c in contracts:
        logging.info("  %s  %s  strike=%.2f", c.symbol, c.contract_type, c.strike)
        engines.append(_build_engine(args, c))

    _flatten_positions(args, [c.symbol for c in contracts])

    # signal.signal(signal.SIGINT, signal_handler)

    # async with asyncio.TaskGroup() as tg:
    #     tg.create_task(
    #         ws_massive_task(
    #             engines=engines,
    #             api_key=args.massive_api_key,
    #             market=Market.Options,
    #         )
    #     )
    #     for engine in engines:
    #         tg.create_task(
    #             poll_clst_task(
    #                 engine=engine,
    #                 url=args.url,
    #                 api_key=args.api_key,
    #                 account=args.account,
    #                 symbol=engine.config.symbol,
    #                 interval=args.poll_interval,
    #             )
    #         )
    #         tg.create_task(timer_task(engine=engine))


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "An example option quoter using Clear Street's Active API. "
            "Bids on calls and offers on puts across a strike range."
        )
    )
    parser.add_argument("underlier", type=str, help="Underlying symbol (e.g. AAPL)")
    parser.add_argument("expiry", type=str, help="Expiry date (YYYY-MM-DD)")
    parser.add_argument("min_strike", type=float, help="Minimum strike (inclusive)")
    parser.add_argument("max_strike", type=float, help="Maximum strike (inclusive)")
    add_common_args(parser)
    parser.add_argument(
        "--bbo-offset-ticks",
        type=int,
        default=2,
        help="Quote this many ticks worse than the current BBO (tick = $0.01). "
             "BUYs sit below best bid, SELLs sit above best ask.",
    )
    # Override the shared defaults: option lots are small, and the $0.01 tick
    # matches the offset unit so target prices round to the intended boundary.
    parser.set_defaults(min_size=1, max_size=2, min_tick=0.01)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
