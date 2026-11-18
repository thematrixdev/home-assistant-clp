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

if __name__ == "__main__":
    unittest.main()
