"""Tests for the pure HDO schedule logic.

Run from the repo root: python3 -m unittest discover -s tests

Fixtures are real excerpts of https://hdo.distribuce24.cz/casy and /region
(downloaded 2026-11-08). Expected windows were read from that raw data by hand.
"""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "egd_hdo"))
import hdo  # noqa: E402  (pure module, importable without Home Assistant)

FIXTURES = Path(__file__).parent / "fixtures"
CASY = json.loads((FIXTURES / "casy_sample.json").read_text(encoding="utf-8"))
REGIONS = json.loads((FIXTURES / "region_sample.json").read_text(encoding="utf-8"))
PRG = ZoneInfo("Europe/Prague")
D25 = "D25d-relé1-TAR"


def at(*args: int) -> datetime:
    """Prague wall-clock time."""
    return datetime(*args, tzinfo=PRG)


class InputTests(unittest.TestCase):
    def test_psc_is_normalized(self) -> None:
        self.assertEqual(hdo.normalize_psc(" 690 02 "), "69002")

    def test_psc_rejects_garbage(self) -> None:
        for bad in ("6900", "690025", "abcde", "", "69002\n1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                hdo.normalize_psc(bad)

    def test_regions_for_psc(self) -> None:
        self.assertEqual(hdo.regions_for_psc(REGIONS, "69002"), ["VERSACOM"])
        self.assertEqual(hdo.regions_for_psc(REGIONS, "37833"), ["VYCHOD", "ZAPAD"])
        self.assertEqual(hdo.regions_for_psc(REGIONS, "11000"), [])


class CatalogTests(unittest.TestCase):
    def test_relay_suffix_applies_to_every_tariff_in_the_list(self) -> None:
        self.assertEqual(
            hdo.split_tariffs("C45d,D45d-relé1-PV"), ["C45d-relé1-PV", "D45d-relé1-PV"]
        )
        self.assertEqual(hdo.split_tariffs("C45d,C46d,D45d"), ["C45d", "C46d", "D45d"])
        self.assertEqual(hdo.split_tariffs("D25d-relé1-TAR"), [D25])

    def test_tariffs_in_region(self) -> None:
        self.assertIn(D25, hdo.tariffs(CASY, "VERSACOM"))
        self.assertIn("D45d-relé2-TUV", hdo.tariffs(CASY, "SM"))
        self.assertNotIn("C45d", hdo.tariffs(CASY, "SM"))  # only with its relay suffix

    def test_codes_for_parents_region(self) -> None:
        options = hdo.codes(CASY, "VERSACOM", D25, today=date(2026, 11, 9))
        self.assertEqual(
            [o.code for o in options],
            ["153", "168", "185", "202", "203", "218", "219", "568"],
        )
        option = next(o for o in options if o.code == "168")
        self.assertEqual(option.name, "A1 B5 DP4 (168)")
        self.assertIn("00:00–06:00, 22:00–24:00", option.label)

    def test_code_names_outside_receiver_regions_use_the_code(self) -> None:
        [option] = hdo.codes(CASY, "TOU", "D61d", today=date(2026, 11, 13))
        self.assertEqual(option.name, "d61")
        self.assertIn("12:00–24:00", option.label)


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s168 = hdo.select_schedule(CASY, "VERSACOM", D25, "168")

    def test_active_window_spans_midnight(self) -> None:
        st = hdo.state_at(self.s168, at(2026, 11, 9, 3, 0))
        self.assertTrue(st.active)
        self.assertEqual(st.start, at(2026, 11, 8, 22, 0))
        self.assertEqual(st.end, at(2026, 11, 9, 6, 0))
        self.assertEqual(st.next_change, at(2026, 11, 9, 6, 0))

    def test_inactive_points_to_next_window(self) -> None:
        st = hdo.state_at(self.s168, at(2026, 11, 14, 12, 0))
        self.assertFalse(st.active)
        self.assertEqual(st.start, at(2026, 11, 14, 22, 0))
        self.assertEqual(st.end, at(2026, 11, 15, 6, 0))
        self.assertEqual(st.next_change, st.start)

    def test_window_end_is_exclusive(self) -> None:
        self.assertFalse(hdo.state_at(self.s168, at(2026, 11, 9, 6, 0)).active)
        self.assertTrue(hdo.state_at(self.s168, at(2026, 11, 9, 22, 0)).active)

    def test_dst_night_lasts_nine_real_hours(self) -> None:
        # 2026-10-25 03:00 CEST -> 02:00 CET; 22:00 to 06:00 is 9 hours that night.
        st = hdo.state_at(self.s168, at(2026, 10, 24, 23, 0))
        self.assertEqual(st.end.astimezone(UTC) - st.start.astimezone(UTC), timedelta(hours=9))

    def test_season_switch_from_sunday_to_monday(self) -> None:
        s153 = hdo.select_schedule(CASY, "VERSACOM", D25, "153")
        st = hdo.state_at(s153, at(2026, 10, 25, 23, 45))  # old season: 23:30-24:00
        self.assertTrue(st.active)
        self.assertEqual(st.end, at(2026, 10, 26, 0, 0))  # new season starts at 00:10
        st = hdo.state_at(s153, at(2026, 10, 26, 0, 5))
        self.assertFalse(st.active)
        self.assertEqual((st.start, st.end), (at(2026, 10, 26, 0, 10), at(2026, 10, 26, 5, 10)))

    def test_unknown_when_egd_has_not_published_yet(self) -> None:
        st = hdo.state_at(self.s168, at(2027, 1, 5, 12, 0))
        self.assertIsNone(st.active)
        self.assertIsNone(st.start)
        # check again at midnight: the next day may be published already
        self.assertEqual(st.next_change, at(2027, 1, 6, 0, 0))

    def test_yearly_season_wraps_over_new_year(self) -> None:
        s = hdo.select_schedule(CASY, "SM", "C46d-relé2-TUV", "AC46")
        st = hdo.state_at(s, at(2027, 1, 11, 19, 0))  # season 11-01..01-31
        self.assertTrue(st.active)
        self.assertEqual((st.start, st.end), (at(2027, 1, 11, 18, 0), at(2027, 1, 11, 20, 0)))

    def test_weekend_tariff_merges_into_one_window(self) -> None:
        s = hdo.select_schedule(CASY, "TOU", "D61d", "d61")
        st = hdo.state_at(s, at(2026, 11, 11, 12, 0))  # Wednesday: no NT Mon-Thu
        self.assertFalse(st.active)
        self.assertEqual((st.start, st.end), (at(2026, 11, 13, 12, 0), at(2026, 11, 15, 22, 0)))

    def test_always_valid_period(self) -> None:
        s = hdo.select_schedule(CASY, "PH", "D45d", "PH20_1")  # 1900-01-01..9999-12-31
        st = hdo.state_at(s, at(2030, 6, 3, 7, 0))  # Monday, gap 06:45-07:45
        self.assertFalse(st.active)
        self.assertEqual((st.start, st.end), (at(2030, 6, 3, 7, 45), at(2030, 6, 3, 8, 45)))

    def test_unknown_code_raises(self) -> None:
        with self.assertRaises(hdo.HdoDataError):
            hdo.select_schedule(CASY, "VERSACOM", D25, "999")


class ValidationTests(unittest.TestCase):
    """The EG.D API is a trust boundary: bad shapes must fail loudly."""

    def _broken(self, mutate) -> list:
        data = copy.deepcopy(CASY)
        entry = next(e for e in data if e["region"] == "VERSACOM" and e["kodHdo_A"] == "168")
        mutate(entry["sazby"][0]["dny"][0])
        return data

    def _assert_rejected(self, data: list) -> None:
        with self.assertRaises(hdo.HdoDataError):
            hdo.select_schedule(data, "VERSACOM", D25, "168")

    def test_bad_time_rejected(self) -> None:
        self._assert_rejected(self._broken(lambda d: d["casy"][0].update(od="25:00:00")))

    def test_reversed_interval_rejected(self) -> None:
        self._assert_rejected(
            self._broken(lambda d: d["casy"][0].update(od="06:00:00", do="05:00:00"))
        )

    def test_bad_weekday_rejected(self) -> None:
        self._assert_rejected(self._broken(lambda d: d.update(denVTydnu=8)))

    def test_top_level_must_be_a_list(self) -> None:
        with self.assertRaises(hdo.HdoDataError):
            hdo.tariffs({"oops": 1}, "VERSACOM")

    def test_junk_rows_are_skipped_in_listings(self) -> None:
        data = [42, "x", {"region": "VERSACOM", "sazby": "nope"}, *CASY]
        self.assertIn(D25, hdo.tariffs(data, "VERSACOM"))
        self.assertEqual(len(hdo.codes(data, "VERSACOM", D25, today=date(2026, 11, 9))), 8)


if __name__ == "__main__":
    unittest.main()
