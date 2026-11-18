from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from backend.search import Listing, SearchQuery, ValidationError, load_listings, relevance, search_listings

TODAY = date(2026, 9, 9)
BASE = Listing("1", "MLS_A", "1 Main St", "Springfield", "VA", "22150",
               500_000, 3, 2, 1500, 38.7, -77.1, TODAY.isoformat(), "active",
               "Sunny home with a fenced yard near Metro.")


def query(**params):
    return SearchQuery.parse({key: [str(value)] for key, value in params.items()})


class SearchTests(unittest.TestCase):
    def test_combined_filters_and_inclusive_price_boundaries(self):
        listings = (BASE, replace(BASE, id="2", price=500_001),
                    replace(BASE, id="3", bedrooms=2),
                    replace(BASE, id="4", city="Reston"),
                    replace(BASE, id="5", description="Garage"),
                    replace(BASE, id="6", price=499_999))
        result = search_listings(listings, query(minPrice=500_000, maxPrice=500_000,
                                                minBedrooms=3, city="SPRINGFIELD", keyword="yard"), TODAY)
        self.assertEqual([item["id"] for item in result["items"]], ["1"])

    def test_city_and_keyword_normalize_case_and_whitespace(self):
        listing = replace(BASE, city="  Falls   Church ", description="Walk to METRO   station")
        result = search_listings((listing,), query(city=" falls church ", keyword=" metro station "), TODAY)
        self.assertEqual(result["total"], 1)

    def test_city_is_exact_not_substring(self):
        result = search_listings((BASE,), query(city="Spring"), TODAY)
        self.assertEqual(result["total"], 0)

    def test_keyword_matches_description_only(self):
        result = search_listings((BASE,), query(keyword="Main"), TODAY)
        self.assertEqual(result["total"], 0)

    def test_no_matches_and_empty_dataset(self):
        for listings, filters in [((BASE,), query(city="Nowhere")), ((), query())]:
            with self.subTest(listings=listings):
                result = search_listings(listings, filters, TODAY)
                self.assertEqual(result["items"], [])
                self.assertEqual(result["total"], 0)
                self.assertEqual(result["totalPages"], 0)
                self.assertEqual(result["page"], 1)

    def test_budget_fit_and_recency_formula(self):
        old = replace(BASE, listedDate=(TODAY - timedelta(days=30)).isoformat())
        self.assertAlmostEqual(relevance(BASE, 500_000, TODAY), 100)
        self.assertAlmostEqual(relevance(old, 500_000, TODAY), 85)
        self.assertAlmostEqual(relevance(BASE, 400_000, TODAY), 82.5)
        self.assertAlmostEqual(relevance(replace(BASE, price=1_000_000), 500_000, TODAY), 30)

    def test_without_budget_ranking_uses_recency(self):
        old = replace(BASE, id="2", listedDate=(TODAY - timedelta(days=30)).isoformat())
        result = search_listings((old, BASE), query(), TODAY)
        self.assertEqual([item["id"] for item in result["items"]], ["1", "2"])
        self.assertEqual([item["relevanceScore"] for item in result["items"]], [100, 50])

    def test_budget_changes_order_without_filtering_out_expensive_listings(self):
        other = replace(BASE, id="2", price=400_000)
        result = search_listings((BASE, other), query(targetBudget=400_000), TODAY)
        self.assertEqual([item["id"] for item in result["items"]], ["2", "1"])
        self.assertEqual(result["total"], 2)

    def test_future_date_is_clamped_to_current_day(self):
        future = replace(BASE, listedDate=(TODAY + timedelta(days=10)).isoformat())
        self.assertEqual(relevance(future, None, TODAY), 100)
        self.assertEqual(relevance(future, 500_000, TODAY), 100)

    def test_scores_remain_in_range(self):
        for age in (0, 30, 300, 100_000):
            for price in (0, 100, 500_000, 100_000_000):
                listing = replace(BASE, price=price, listedDate=(TODAY - timedelta(days=age)).isoformat())
                for budget in (None, 0.01, 500_000):
                    with self.subTest(age=age, price=price, budget=budget):
                        score = relevance(listing, budget, TODAY)
                        self.assertGreaterEqual(score, 0)
                        self.assertLessEqual(score, 100)

    def test_ties_use_source_then_id_independent_of_input_order(self):
        a2 = replace(BASE, id="2")
        b1 = replace(BASE, source="MLS_B")
        for listings in [(b1, a2, BASE), (BASE, b1, a2)]:
            result = search_listings(listings, query(), TODAY)
            self.assertEqual([(item["source"], item["id"]) for item in result["items"]],
                             [("MLS_A", "1"), ("MLS_A", "2"), ("MLS_B", "1")])

    def test_raw_score_not_rounded_score_determines_order(self):
        worse = replace(BASE, id="0", price=500_001)
        result = search_listings((worse, BASE), query(targetBudget=500_000), TODAY)
        self.assertEqual([item["id"] for item in result["items"]], ["1", "0"])
        self.assertEqual(result["items"][0]["relevanceScore"], result["items"][1]["relevanceScore"])

    def test_pagination_boundaries_and_stability(self):
        listings = tuple(replace(BASE, id=str(i)) for i in range(5))
        pages = [search_listings(listings, query(page=i, pageSize=2), TODAY) for i in range(1, 5)]
        self.assertEqual([len(page["items"]) for page in pages], [2, 2, 1, 0])
        self.assertTrue(all(page["total"] == 5 and page["totalPages"] == 3 for page in pages))
        self.assertEqual([item["id"] for page in pages for item in page["items"]], list("01234"))

    def test_all_statuses_and_distinct_feed_records_are_preserved(self):
        listings = (BASE, replace(BASE, source="MLS_B"), replace(BASE, id="3", status="pending"),
                    replace(BASE, id="4", status="sold"))
        self.assertEqual(search_listings(listings, query(), TODAY)["total"], 4)

    def test_search_does_not_mutate_listings(self):
        listings = (BASE,)
        result = search_listings(listings, query(), TODAY)
        result["items"][0]["price"] = 0
        self.assertEqual(BASE.price, 500_000)

    def test_supplied_sample_loads_and_searches(self):
        listings = load_listings(Path(__file__).resolve().parents[2] / "sample_listings.json")
        self.assertEqual(len(listings), 12)
        result = search_listings(listings, query(city="Springfield", minBedrooms=3), TODAY)
        self.assertEqual(result["total"], 2)

    def test_duplicate_source_id_is_rejected_during_load(self):
        import json
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "listings.json"
            path.write_text(json.dumps([asdict(BASE), asdict(BASE)]))
            with self.assertRaisesRegex(ValueError, "unique"):
                load_listings(path)


class ValidationTests(unittest.TestCase):
    def test_defaults_and_blank_text_filters(self):
        self.assertEqual(query().page_size, 6)
        self.assertEqual(query().page, 1)
        self.assertEqual(query(city="  ", keyword=" ").city, "")

    def test_zero_and_decimal_filter_values(self):
        parsed = query(minPrice=0, maxPrice=500000.25, minBedrooms=0, targetBudget=0.01)
        self.assertEqual(parsed.min_price, 0)
        self.assertEqual(parsed.max_price, 500000.25)
        self.assertEqual(parsed.min_bedrooms, 0)

    def test_invalid_numeric_inputs(self):
        cases = {
            "minPrice": ["-1", "", "abc", "NaN", "Infinity", "-Infinity", "1e999"],
            "maxPrice": ["-1", "NaN", "abc"],
            "targetBudget": ["0", "-1", "NaN", "Infinity", "abc"],
            "minBedrooms": ["-1", "1.5", "3.0", "abc", ""],
            "page": ["0", "-1", "1.5", "abc"],
            "pageSize": ["0", "-1", "101", "2.5", "abc"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError) as raised:
                        query(**{field: value})
                    self.assertEqual(raised.exception.field, field)

    def test_reversed_price_range(self):
        with self.assertRaisesRegex(ValidationError, "Minimum price"):
            query(minPrice=2, maxPrice=1)

    def test_repeated_and_unknown_parameters(self):
        for params in [{"city": ["Reston", "Fairfax"]}, {"minprice": ["100"]}]:
            with self.subTest(params=params):
                with self.assertRaises(ValidationError):
                    SearchQuery.parse(params)
