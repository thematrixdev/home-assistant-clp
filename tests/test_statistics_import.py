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

    def test_daily_calibration_exact_sum(self):
        # 24 hours of raw data summing to 5.5
        raw_hours = [0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.6, 0.4, 0.3, 0.2, 0.1, 0.1, 0.2, 0.3, 0.6, 0.4, 0.3, 0.3, 0.3, 0.2]
        self.assertEqual(sum(raw_hours), 5.5)

        daily_target = 5.3
        day_hours = {datetime.datetime(2026, 11, 17, i, 0, 0): raw_hours[i] for i in range(24)}

        raw_sum = sum(day_hours.values())
        ratio = daily_target / raw_sum
        scaled_hours = {ts: round(val * ratio, 4) for ts, val in day_hours.items()}
        diff = round(daily_target - sum(scaled_hours.values()), 4)
        peak_ts = max(day_hours.keys(), key=lambda ts: day_hours[ts])
        scaled_hours[peak_ts] = round(scaled_hours[peak_ts] + diff, 4)

        calibrated_sum = round(sum(scaled_hours.values()), 4)
        self.assertEqual(calibrated_sum, daily_target)

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
