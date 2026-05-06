import sys

sys.path.append("..")

import signal
import argparse
import asyncio
import logging

from maker.engine import Engine
from common.models import EngineConfig
from common import add_common_args, ws_massive_task, poll_clst_task, timer_task

engine: Engine = None

def signal_handler(sig, frame):
    engine.cancel_all_orders()
    logging.info("Dumping stats...")
    engine.dump_stats()
    sys.exit(0)

async def main(args):
    global engine

    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )

    config = EngineConfig(
        url=args.url,
        api_key=args.api_key,
        account=args.account,
        symbol=args.symbol,
        max_position=args.max_position,
        min_tick=args.min_tick,
        min_size=args.min_size,
        max_size=args.max_size,
        max_rejects=4,
    )
    engine = Engine(config=config, min_edge=args.min_edge, num_levels=args.levels)

    signal.signal(signal.SIGINT, signal_handler)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(
            ws_massive_task(
                engine=engine, symbols=[args.symbol], api_key=args.massive_api_key
            )
        )
        tg.create_task(
            poll_clst_task(
                engine=engine,
                url=args.url,
                api_key=args.api_key,
                account=args.account,
                symbol=args.symbol,
                interval=args.poll_interval,
            )
        )
        tg.create_task(timer_task(engine=engine))


def parse_args():
    parser = argparse.ArgumentParser(
        description="An example maker bot using Clear Street Studio's APIs"
    )
    parser.add_argument("symbol", type=str, help="The symbol to trade")
    add_common_args(parser)

    parser.add_argument(
        "--levels", type=int, help="Number of levels to quote", default=3
    )
    parser.add_argument(
        "--min-edge", type=float, help="Minimum edge around theo", default=0.50
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
