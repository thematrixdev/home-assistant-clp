import unittest
import datetime
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "clphk"),
)

from const import calculate_residential_bill

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

    def test_raw_hourly_statistics(self):
        # Hourly data is 100% raw unmodified values
        raw_hours = [0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.6, 0.4, 0.3, 0.2, 0.1, 0.1, 0.2, 0.3, 0.6, 0.4, 0.3, 0.3, 0.3, 0.2]
        records = [{"start": datetime.datetime(2026, 11, 17, i, 0, 0), "kwh": raw_hours[i]} for i in range(24)]
        
        raw_by_utc = {r["start"]: round(r["kwh"], 4) for r in records}
        self.assertEqual(len(raw_by_utc), 24)
        self.assertEqual(raw_by_utc[datetime.datetime(2026, 11, 17, 10, 0, 0)], 0.6)
        # Running sum test
        running_sum = 0.0
        for ts in sorted(raw_by_utc.keys()):
            running_sum = round(running_sum + raw_by_utc[ts], 4)
        self.assertEqual(running_sum, 5.5)

    def test_daily_statistics_parsing_and_sum(self):
        # Daily records parsed directly from CLP Daily API
        daily_results = [
            {"startDate": "20261115000000", "expireDate": "20261115235959", "kwhTotal": 6.3},
            {"startDate": "20261116000000", "expireDate": "20261116235959", "kwhTotal": 6.0},
            {"startDate": "20261117000000", "expireDate": "20261117235959", "kwhTotal": 5.3},
        ]
        daily_by_utc = {}
        for r in daily_results:
            dt = datetime.datetime.strptime(r["startDate"][:8], "%Y%m%d")
            daily_by_utc[dt] = float(r["kwhTotal"])
            
        self.assertEqual(len(daily_by_utc), 3)
        self.assertEqual(daily_by_utc[datetime.datetime(2026, 11, 17)], 5.3)
        
        base_sum = 100.0
        running_sum = base_sum
        for ts in sorted(daily_by_utc.keys()):
            running_sum = round(running_sum + daily_by_utc[ts], 4)
        self.assertEqual(running_sum, 117.6)

    def test_timestamp_hour_shift(self):
        # CLP reports 01:00 for 00:00-01:00
        clp_startDate = "20261117010000"
        clp_dt = datetime.datetime.strptime(clp_startDate, "%Y%m%d%H%M%S")
        hour_start = clp_dt - datetime.timedelta(hours=1)
        self.assertEqual(hour_start.hour, 0)
        self.assertEqual(hour_start.day, 17)

        # CLP reports 20261118000000 for 23:00-24:00 on 20261117
        clp_end_day = "20261118000000"
        clp_dt_end = datetime.datetime.strptime(clp_end_day, "%Y%m%d%H%M%S")
        hour_start_end = clp_dt_end - datetime.timedelta(hours=1)
        self.assertEqual(hour_start_end.hour, 23)
        self.assertEqual(hour_start_end.day, 17)

    def test_calculate_residential_bill(self):
        # Test Case 1: 296.8 kWh over 61 days (Tier 1 <= 400 kWh, rebate applied)
        res1 = calculate_residential_bill(296.8, 61, 42.9028)
        self.assertEqual(res1["total"], 359.73)
        self.assertEqual(res1["effective_rate"], 1.212)
        
        # Test Case 2: 616.0 kWh over 61 days (Crosses into Tier 2, no rebate)
        res2 = calculate_residential_bill(616.0, 61, 37.0)
        self.assertEqual(round(res2["total"]), 839)
        self.assertEqual(res2["effective_rate"], 1.362)

        # Test Case 3: Minimum charge 40 HKD
        res3 = calculate_residential_bill(5.0, 60, 39.4)
        self.assertEqual(res3["total"], 40.0)

        # Test Case 4: Special fuel rebate (8 cents/kWh deduction)
        res4 = calculate_residential_bill(300.0, 60, 46.2, special_fuel_rebate_cents=8.0)
        # basic: 300 * 0.945 = 283.50, fuel: 300 * 0.462 = 138.60, rebate: 300 * 0.162 = 48.60, special: 300 * 0.08 = 24.00
        # net: 283.50 + 138.60 - 48.60 - 24.00 = 349.50
        self.assertEqual(res4["total"], 349.50)
        self.assertEqual(res4["special_rebate"], 24.00)

        # Test Case 5: Government subsidy (e.g. 50 HKD deduction)
        res5 = calculate_residential_bill(300.0, 60, 46.2, subsidy=50.0)
        self.assertEqual(res5["total"], 323.50)
        self.assertEqual(res5["subsidy"], 50.00)

        # Test Case 6: Custom fixed rate (e.g. 1.25 HKD/kWh flat)
        res6 = calculate_residential_bill(200.0, 60, custom_fixed_rate=1.25)
        self.assertEqual(res6["total"], 250.00)
        self.assertEqual(res6["effective_rate"], 1.25)

        # Test Case 7: Low consumption (< 30 kWh) avoids minimum bill rate spike
        res7 = calculate_residential_bill(5.0, 60, 47.4)
        self.assertEqual(res7["total"], 40.0)
        # Should not spike to 40 / 5 = 8.0, but stay close to standard per-kWh rate (~1.247)
        self.assertLess(res7["effective_rate"], 2.0)
        self.assertGreater(res7["effective_rate"], 1.0)

if __name__ == "__main__":
    unittest.main()
