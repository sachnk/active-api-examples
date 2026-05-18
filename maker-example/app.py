import sys

sys.path.append("..")

import signal
import argparse
import asyncio
import logging

from maker.engine import Engine
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

def _build_engine(args, symbol: str, side: str) -> Engine:
    config = EngineConfig(
        url=args.url,
        api_key=args.api_key,
        account=args.account,
        symbol=symbol,
        max_position=args.max_position,
        min_tick=args.min_tick,
        min_size=args.min_size,
        max_size=args.max_size,
        max_rejects=4,
    )
    return Engine(
        config=config, side=side, min_edge=args.min_edge, num_levels=args.levels
    )

async def main(args):
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )

    engines.append(_build_engine(args, args.s1, "BUY"))
    engines.append(_build_engine(args, args.s2, "SELL"))

    signal.signal(signal.SIGINT, signal_handler)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(ws_massive_task(engines=engines, api_key=args.massive_api_key))
        for engine in engines:
            tg.create_task(
                poll_clst_task(
                    engine=engine,
                    url=args.url,
                    api_key=args.api_key,
                    account=args.account,
                    symbol=engine.config.symbol,
                    interval=args.poll_interval,
                )
            )
            tg.create_task(timer_task(engine=engine))


def parse_args():
    parser = argparse.ArgumentParser(
        description="An example single-sided maker bot using Clear Street's Active API"
    )
    parser.add_argument("s1", type=str, help="The symbol to BUY (bid-side only)")
    parser.add_argument("s2", type=str, help="The symbol to SELL (ask-side only)")
    add_common_args(parser)

    parser.add_argument(
        "--levels", type=int, help="Number of levels to quote per side", default=3
    )
    parser.add_argument(
        "--min-edge", type=float, help="Minimum edge around theo", default=0.50
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
