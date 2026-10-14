"""Clock-time output and live countdown behaviour."""

import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone

DISPLAY_PATH = (
    Path(__file__).resolve().parents[1]
    / 'custom_components'
    / 'washing_machine_energy_pattern_recognition'
    / 'display.py'
)
_spec = importlib.util.spec_from_file_location('washer_display', DISPLAY_PATH)
_display = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_display)


class DisplayTests(unittest.TestCase):
    def test_clock_time_is_local_not_relative(self):
        stamp = datetime(2026, 10, 14, 14, 32, tzinfo=timezone.utc).timestamp()
        self.assertEqual(_display.format_finish_clock(stamp, 'Europe/Berlin'), '16:32')
        self.assertEqual(_display.format_finish_clock(stamp, 'Europe/London'), '15:32')

    def test_clock_follows_winter_timezone(self):
        stamp = datetime(2026, 12, 14, 14, 32, tzinfo=timezone.utc).timestamp()
        self.assertEqual(_display.format_finish_clock(stamp, 'Europe/Berlin'), '15:32')

    def test_remaining_minutes_count_down(self):
        self.assertEqual(_display.minutes_until(1000, 100), 15)
        self.assertEqual(_display.minutes_until(1000, 160), 14)
        self.assertEqual(_display.minutes_until(1000, 999), 1)
        self.assertEqual(_display.minutes_until(1000, 1000), 0)
        self.assertEqual(_display.minutes_until(1000, 2000), 0)


if __name__ == '__main__':
    unittest.main()
