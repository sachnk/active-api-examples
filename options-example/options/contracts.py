import logging
from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class Contract:
    symbol: str         # OSI with spaces, e.g. "AAPL  260320C00180000"
    contract_type: str  # "CALL" or "PUT"
    strike: float
    expiry: str         # YYYY-MM-DD


def fetch_contracts(
    url: str,
    api_key: str,
    underlier: str,
    expiry: str,
    contract_type: Optional[str] = None,
) -> List[Contract]:
    """GET /instruments/options/contracts, paginating until exhausted."""
    out: List[Contract] = []
    headers = {"Authorization": f"Bearer {api_key}"}
    page_token: Optional[str] = None
    while True:
        params = {
            "underlier": underlier,
            "expiry": expiry,
            "page_size": 1000,
        }
        if contract_type is not None:
            params["contract_type"] = contract_type
        if page_token is not None:
            params["page_token"] = page_token

        resp = requests.get(
            f"{url}/instruments/options/contracts",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        for row in body.get("data", []):
            out.append(
                Contract(
                    symbol=row["symbol"],
                    contract_type=row["contract_type"],
                    strike=float(row["strike_price"]),
                    expiry=row["expiry"],
                )
            )
        page_token = body.get("metadata", {}).get("next_page_token")
        if not page_token:
            break

    return out


def filter_strikes(
    contracts: List[Contract], min_strike: float, max_strike: float
) -> List[Contract]:
    keep = [c for c in contracts if min_strike <= c.strike <= max_strike]
    keep.sort(key=lambda c: (c.strike, c.contract_type))
    logging.info(
        "filtered %d/%d contracts in strike range [%.2f, %.2f]",
        len(keep), len(contracts), min_strike, max_strike,
    )
    return keep
