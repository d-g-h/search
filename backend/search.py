"""Pure filtering, relevance scoring, and pagination. No HTTP dependencies."""

from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from pathlib import Path
import re


class ValidationError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class Listing:
    id: str
    source: str
    address: str
    city: str
    state: str
    zip: str
    price: float
    bedrooms: int
    bathrooms: float
    sqft: int
    latitude: float
    longitude: float
    listedDate: str
    status: str
    description: str


def load_listings(path: Path) -> tuple[Listing, ...]:
    with path.open(encoding="utf-8") as file:
        rows = json.load(file)
    listings = tuple(Listing(**row) for row in rows)
    keys = [(listing.source, listing.id) for listing in listings]
    if len(keys) != len(set(keys)):
        raise ValueError("Each listing must have a unique (source, id) pair.")
    for listing in listings:
        date.fromisoformat(listing.listedDate)
    return listings


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True)
class SearchQuery:
    min_price: float | None = None
    max_price: float | None = None
    min_bedrooms: int | None = None
    city: str = ""
    keyword: str = ""
    target_budget: float | None = None
    page: int = 1
    page_size: int = 6

    @classmethod
    def parse(cls, params: dict[str, list[str]]) -> "SearchQuery":
        allowed = {"minPrice", "maxPrice", "minBedrooms", "city", "keyword", "targetBudget", "page", "pageSize"}
        for field, values in params.items():
            if field not in allowed:
                raise ValidationError(field, f"Unknown parameter: {field}.")
            if len(values) != 1:
                raise ValidationError(field, f"Supply {field} only once.")

        def number(field: str, *, integer: bool = False, default=None):
            if field not in params:
                return default
            raw = params[field][0].strip()
            try:
                if integer and not re.fullmatch(r"[0-9]+", raw):
                    raise ValueError
                value = int(raw) if integer else float(raw)
                if not math.isfinite(value):
                    raise ValueError
            except (ValueError, OverflowError):
                kind = "whole number" if integer else "finite number"
                raise ValidationError(field, f"{field} must be a {kind}.") from None
            if value < 0:
                raise ValidationError(field, f"{field} must not be negative.")
            return value

        min_price = number("minPrice")
        max_price = number("maxPrice")
        target_budget = number("targetBudget")
        min_bedrooms = number("minBedrooms", integer=True)
        page = number("page", integer=True, default=1)
        page_size = number("pageSize", integer=True, default=6)
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValidationError("minPrice", "Minimum price must be less than or equal to maximum price.")
        if target_budget is not None and target_budget <= 0:
            raise ValidationError("targetBudget", "Target budget must be greater than zero.")
        if page < 1:
            raise ValidationError("page", "Page must be at least 1.")
        if not 1 <= page_size <= 100:
            raise ValidationError("pageSize", "Page size must be between 1 and 100.")
        return cls(
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            city=normalize(params.get("city", [""])[0]),
            keyword=normalize(params.get("keyword", [""])[0]),
            target_budget=target_budget,
            page=page,
            page_size=page_size,
        )


def relevance(listing: Listing, budget: float | None, today: date) -> float:
    """0–100 score: 70% budget fit + 30% recency, or recency only without a budget."""
    age = max(0, (today - date.fromisoformat(listing.listedDate)).days)
    recency = 2 ** (-age / 30)
    if budget is None:
        return 100 * recency
    budget_fit = max(0, 1 - abs(listing.price - budget) / budget)
    return 100 * (0.7 * budget_fit + 0.3 * recency)


def search_listings(listings: tuple[Listing, ...], query: SearchQuery, today: date) -> dict:
    matches = []
    for listing in listings:
        if query.min_price is not None and listing.price < query.min_price:
            continue
        if query.max_price is not None and listing.price > query.max_price:
            continue
        if query.min_bedrooms is not None and listing.bedrooms < query.min_bedrooms:
            continue
        if query.city and normalize(listing.city) != query.city:
            continue
        if query.keyword and query.keyword not in normalize(listing.description):
            continue
        matches.append((listing, relevance(listing, query.target_budget, today)))

    # Sort before rounding. The source and ID break ties consistently across pages.
    matches.sort(key=lambda item: (-item[1], item[0].source, item[0].id))
    total = len(matches)
    start = (query.page - 1) * query.page_size
    page = matches[start : start + query.page_size]
    items = [
        {**asdict(listing), "relevanceScore": round(score, 2)}
        for listing, score in page
    ]
    return {
        "items": items,
        "total": total,
        "page": query.page,
        "pageSize": query.page_size,
        "totalPages": (total + query.page_size - 1) // query.page_size,
        "asOf": today.isoformat(),
    }
