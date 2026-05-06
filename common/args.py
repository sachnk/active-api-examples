import os
from argparse import ArgumentParser


def add_common_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--max-position",
        type=int,
        help="Maximum position to hold, long or short",
        default=300,
    )
    parser.add_argument(
        "--min-size", type=int, help="Minimum size for orders", default=160
    )
    parser.add_argument(
        "--max-size", type=int, help="Maximum size for orders", default=200
    )
    parser.add_argument(
        "--min-tick", type=float, help="Minimum price tick", default=0.05
    )

    url = os.environ.get("CLEAR_STREET_URL", "https://api-active.clearstreet.io/active/v1")
    parser.add_argument(
        "--url",
        type=str,
        help="Base URL for Clear Street Active API",
        required=url is None,
        default=url,
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        help="Interval (seconds) to poll for order/position updates",
        default=1.0,
    )

    api_key = os.environ.get("CLEAR_STREET_API_KEY")
    parser.add_argument(
        "--api-key",
        type=str,
        help="Clear Street API key (sent as Authorization: Bearer <key>)",
        required=api_key is None,
        default=api_key,
    )

    account = os.environ.get("CLEAR_STREET_ACCOUNT")
    parser.add_argument(
        "--account",
        type=str,
        help="Clear Street account ID (numeric)",
        required=account is None,
        default=account,
    )

    massive = os.environ.get("MASSIVE_API_KEY")
    parser.add_argument(
        "--massive-api-key",
        type=str,
        help="Massive (formerly Polygon.io) API key",
        required=massive is None,
        default=massive,
    )
