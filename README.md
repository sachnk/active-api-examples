# Active API Examples

This project contains examples of using the Clear Street Active [API](https://docs.clearstreet.com/api). These examples are for illustrative purposes only, and not intended for production use.

## Prequisites

You need at least python 3.12 and poetry 1.8.2 to run the examples. In addition, for market-data, you need an API key from [Massive](https://massive.com) (formerly Polygon.io).

## Maker Example

This example passively layers the book with several orders.

```
$ poetry install
$ cd maker-example
$ poetry run python3 app.py AAPL --url https://api-active.clearstreet.io/active/v1 --account <your-account> --massive-api-key <massive-api-key> --api-key <api-key>
```

This will launch a quoting engine for `AAPL`. It will maintain 5 price-levels on both buy/sell sides.

Order/position state is polled from the REST API every second by default; use `--poll-interval` to change the cadence.
