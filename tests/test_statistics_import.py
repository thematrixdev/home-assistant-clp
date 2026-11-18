import unittest
import datetime

class TestStatisticsImport(unittest.TestCase):
    def test_dedup_and_sort(self):
        records = [
            {"start": datetime.datetime(2026, 11, 18, 1, 0, 0), "kwh": 0.1},
            {"start": datetime.datetime(2026, 11, 18, 2, 0, 0), "kwh": 0.2},
            {"start": datetime.datetime(2026, 11, 18, 1, 0, 0), "kwh": 0.15}, # Duplicate start
        ]
        deduped = {}
        for r in sorted([r for r in records if r.get("start") and r.get("kwh") is not None], key=lambda x: x["start"]):
            start_utc = r["start"].replace(minute=0, second=0, microsecond=0)
            deduped[start_utc] = r["kwh"] or 0.0

        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[datetime.datetime(2026, 11, 18, 1, 0, 0)], 0.15)
        self.assertEqual(deduped[datetime.datetime(2026, 11, 18, 2, 0, 0)], 0.2)

if __name__ == "__main__":
    unittest.main()
