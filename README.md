# Active API Examples

This project contains examples of using the Clear Street Active [API](https://docs.clearstreet.com/api). These examples are for illustrative purposes only, and not intended for production use.

## Prequisites

You need at least python 3.12 and poetry 1.8.2 to run the examples. In addition, for market-data, you need an API key from [Massive](https://massive.com) (formerly Polygon.io).

## Maker Example

This example passively layers the book with several orders on each of two symbols — buys only on the first, sells only on the second. Quoting only one side of each name avoids the API's non-flipping constraint by construction.

```
$ poetry install
$ cd maker-example
$ poetry run python3 app.py AAPL MSFT --url https://api-active.clearstreet.io/active/v1 --account <your-account> --massive-api-key <massive-api-key> --api-key <api-key>
```

This will launch two quoting engines: bids on `AAPL` and asks on `MSFT`. Each maintains `--levels` price-levels around its symbol's theo.

Order/position state is polled from the REST API every second by default; use `--poll-interval` to change the cadence.
