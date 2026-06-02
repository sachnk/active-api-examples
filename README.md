# Active API Examples

This project contains examples of using the Clear Street Active [API](https://docs.clearstreet.com/api). These examples are for illustrative purposes only, and not intended for production use.

## Prequisites

You need at least python 3.12 and poetry 1.8.2 to run the examples. In addition, for market-data, you need an API key from [Massive](https://massive.com) (formerly Polygon.io).

## Stock Example

This example passively layers the book with several orders on each of two symbols — buys only on the first, sells only on the second. Quoting only one side of each name avoids the API's non-flipping constraint by construction.

```
$ poetry install
$ cd stock-example
$ poetry run python3 app.py AAPL MSFT --url https://api-active.clearstreet.io/active/v1 --account <your-account> --massive-api-key <massive-api-key> --api-key <api-key>
```

This will launch two quoting engines: bids on `AAPL` and asks on `MSFT`. Each maintains `--levels` price-levels around its symbol's theo.

Order/position state is polled from the REST API every second by default; use `--poll-interval` to change the cadence.

## Options Example

This example quotes option contracts on a single underlier across a strike range. It bids on calls and offers on puts (single-sided per contract, so positions can never flip). Each quote matches the current best bid (for calls) or ask (for puts) from Massive's options feed; whenever the BBO moves, the existing order is cancelled and a new one is placed at the new target.

```
$ poetry install
$ cd options-example
$ poetry run python3 app.py AAPL 2026-06-19 180 200 --url https://api-active.clearstreet.io/active/v1 --account <your-account> --massive-api-key <massive-api-key> --api-key <api-key>
```

Arguments are `<underlier> <expiry YYYY-MM-DD> <min_strike> <max_strike>`. At startup the example calls `GET /instruments/options/contracts` to discover which strikes are actually listed in the range, then spawns one engine per call (BUY) and one per put (SELL). Up to `2 × N` engines for N strikes — keep the range tight unless you want a lot of WS subscriptions and poll traffic.

By default each engine quotes 2 ticks worse than the current BBO (where a tick is $0.01) — BUYs sit 2¢ below the best bid, SELLs sit 2¢ above the best ask. Tune with `--bbo-offset-ticks N` (use `0` to match the BBO exactly).
