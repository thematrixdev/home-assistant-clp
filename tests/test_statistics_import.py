import unittest
import datetime
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "clphk"),
)

from const import (
    DEFAULT_TIER_LIMITS,
    DEFAULT_TIER_RATES,
    calculate_residential_bill,
    parse_comma_floats,
    reconcile_tariff_tiers,
)

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

        # Test Case 8: Custom tier rates and limits
        custom_rates = [1.00, 1.20, 1.40, 1.60, 1.80, 2.00, 2.20] # in HKD/kWh
        custom_limits = [300.0, 500.0, 700.0, 700.0, 700.0, 700.0]
        res8 = calculate_residential_bill(200.0, 60, fuel_cents=47.4, tier_rates=custom_rates, tier_limits=custom_limits)
        # 200 kWh <= 300 (tier 1): basic = 200 * 1.00 = 200 HKD (20000 cents)
        # fuel = 200 * 0.474 = 94.8 HKD
        # rebate (200 kWh <= 200): 200 * 0.172 = 34.4 HKD
        # net = 200 + 94.8 - 34.4 = 260.40 HKD
        self.assertEqual(res8["total"], 260.40)
        self.assertEqual(res8["basic_tariff"], 200.00)

        # Test Case 9: parse_comma_floats (English and Chinese commas)
        self.assertEqual(parse_comma_floats("0.945, 1.079, 1.237"), [0.945, 1.079, 1.237])
        self.assertEqual(parse_comma_floats("0.945，1.079，1.237"), [0.945, 1.079, 1.237])
        self.assertEqual(parse_comma_floats([400, 600, 800]), [400.0, 600.0, 800.0])
        self.assertIsNone(parse_comma_floats(""))
        self.assertIsNone(parse_comma_floats(None))
        self.assertIsNone(parse_comma_floats("abc, def"))

        # Test Case 10: days <= 0 defensive boundary
        res10 = calculate_residential_bill(100.0, 0, 47.4)
        self.assertGreater(res10["total"], 0)

    def test_reconcile_tariff_tiers(self):
        # 1. Default (None, None): returns 7 rates and 6 limits
        rates, limits = reconcile_tariff_tiers(None, None)
        self.assertEqual(len(rates), 7)
        self.assertEqual(len(limits), 6)
        self.assertEqual(rates, DEFAULT_TIER_RATES)
        self.assertEqual(limits, DEFAULT_TIER_LIMITS)

        # 2. 3 custom rates, no limits: adapts first 2 limits from default
        rates, limits = reconcile_tariff_tiers(custom_rates=[1.0, 1.5, 2.0], custom_limits=None)
        self.assertEqual(rates, [1.0, 1.5, 2.0])
        self.assertEqual(limits, [400.0, 600.0])

        # 3. 3 custom rates, 2 custom limits: matches 1-to-1
        rates, limits = reconcile_tariff_tiers(custom_rates=[1.0, 1.5, 2.0], custom_limits=[200.0, 300.0])
        self.assertEqual(rates, [1.0, 1.5, 2.0])
        self.assertEqual(limits, [200.0, 300.0])

        # 4. 3 custom rates, 3 custom limits (over-specified): truncated to 2 limits
        rates, limits = reconcile_tariff_tiers(custom_rates=[1.0, 1.5, 2.0], custom_limits=[200.0, 300.0, 400.0])
        self.assertEqual(rates, [1.0, 1.5, 2.0])
        self.assertEqual(limits, [200.0, 300.0])

        # 5. 1 flat custom rate: 0 limits
        rates, limits = reconcile_tariff_tiers(custom_rates=[1.25], custom_limits=None)
        self.assertEqual(rates, [1.25])
        self.assertEqual(limits, [])

        # 6. Custom limits only (e.g. 2 limits): adapts first 3 rates from default
        rates, limits = reconcile_tariff_tiers(custom_rates=None, custom_limits=[250.0, 350.0])
        self.assertEqual(rates, [0.945, 1.079, 1.237])
        self.assertEqual(limits, [250.0, 350.0])

        # 7. Adaptive to CLP fetched arbitrary N tiers (e.g. 4 tiers)
        base_rates = [0.9, 1.2, 1.6, 2.0]
        base_limits = [500.0, 500.0, 500.0]
        rates, limits = reconcile_tariff_tiers(None, None, base_rates=base_rates, base_limits=base_limits)
        self.assertEqual(rates, [0.9, 1.2, 1.6, 2.0])
        self.assertEqual(limits, [500.0, 500.0, 500.0])

    def test_adaptive_calculate_residential_bill(self):
        # 3-tier custom pricing: Tier 1: <= 200 kWh @ 1.0 HKD, Tier 2: 201-500 kWh @ 1.5 HKD, Tier 3: > 500 kWh @ 2.0 HKD
        rates = [1.0, 1.5, 2.0]
        limits = [200.0, 300.0]

        # Consump 150 kWh (Tier 1): 150 * 1.00 = 150 HKD (15000 cents)
        # fuel: 150 * 0.40 = 60 HKD
        # rebate (150 <= 200): 150 * 0.172 = 25.80 HKD
        # net = 150 + 60 - 25.80 = 184.20 HKD
        res_t1 = calculate_residential_bill(150.0, 60, fuel_cents=40.0, tier_rates=rates, tier_limits=limits)
        self.assertEqual(res_t1["basic_tariff"], 150.00)
        self.assertEqual(res_t1["total"], 184.20)

        # Consump 350 kWh (Crosses into Tier 2: 200 @ 1.0, 150 @ 1.5):
        # basic: 200 * 1.0 + 150 * 1.5 = 200 + 225 = 425 HKD
        # fuel: 350 * 0.40 = 140 HKD
        # rebate (301..400): 350 * 0.152 = 53.20 HKD
        # net = 425 + 140 - 53.20 = 511.80 HKD
        res_t2 = calculate_residential_bill(350.0, 60, fuel_cents=40.0, tier_rates=rates, tier_limits=limits)
        self.assertEqual(res_t2["basic_tariff"], 425.00)
        self.assertEqual(res_t2["total"], 511.80)

        # Consump 700 kWh (Crosses into Tier 3: 200 @ 1.0, 300 @ 1.5, 200 @ 2.0):
        # basic: 200 * 1.0 + 300 * 1.5 + 200 * 2.0 = 200 + 450 + 400 = 1050 HKD
        # fuel: 700 * 0.40 = 280 HKD
        # rebate: 0 (700 > 400)
        # net = 1050 + 280 = 1330.00 HKD
        res_t3 = calculate_residential_bill(700.0, 60, fuel_cents=40.0, tier_rates=rates, tier_limits=limits)
        self.assertEqual(res_t3["basic_tariff"], 1050.00)
        self.assertEqual(res_t3["total"], 1330.00)

        # 1-tier flat pricing via tier_rates=[1.20]
        res_flat = calculate_residential_bill(500.0, 60, fuel_cents=40.0, tier_rates=[1.20])
        # basic: 500 * 1.20 = 600 HKD
        # fuel: 500 * 0.40 = 200 HKD
        # net = 600 + 200 = 800.00 HKD
        self.assertEqual(res_flat["basic_tariff"], 600.00)
        self.assertEqual(res_flat["total"], 800.00)

if __name__ == "__main__":
    unittest.main()
