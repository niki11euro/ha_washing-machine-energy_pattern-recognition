"""Pure standard-library tests, runnable without a Home Assistant install."""

import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'washing_machine_energy_pattern_recognition'
PKG = 'wash_pattern_test'
pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg


def load_module(name):
    spec = importlib.util.spec_from_file_location(f'{PKG}.{name}', ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_module('model')
storage_module = load_module('storage')
Reading = model.Reading
Bin = model.Bin


class ModellingTests(unittest.TestCase):
    def test_irregular_sampling_and_energy(self):
        readings = [Reading(0, 100), Reading(10, 200), Reading(40, 0)]
        bins = model.resample(readings, 0, 60, 30)
        self.assertEqual(len(bins), 2)
        self.assertAlmostEqual(bins[0].mean, 166.6667, places=2)
        self.assertAlmostEqual(bins[1].mean, 66.6667, places=2)
        self.assertAlmostEqual(model.energy_kwh(readings, 0, 60), 7000 / 3_600_000, places=6)

    def test_start_stop_dwell_and_mid_cycle_pause(self):
        points = [Reading(0, 0), Reading(30, 30), Reading(600, 1),
                  Reading(900, 50), Reading(1600, 0), Reading(2400, 0)]
        cycles = model.detect_completed_cycles(points, 2400, end_hold=480, min_duration=600)
        self.assertEqual(cycles, [(30, 1600)])

    def test_short_noise_is_not_a_cycle(self):
        points = [Reading(0, 0), Reading(15, 10), Reading(23, 0), Reading(600, 0)]
        self.assertFalse(model.detect_completed_cycles(points, 600))

    def test_dct_size(self):
        self.assertEqual(len(model.dct_coefficients([Bin(3, 5)] * 120)), 24)

    def test_matching_and_rejecting(self):
        ref = [Bin(20, 30)] * 10 + [Bin(1900, 2000)] * 10 + [Bin(50, 60)] * 35
        other = [Bin(3, 5)] * 20 + [Bin(1900, 2000)] * 12 + [Bin(80, 90)] * 50
        history = [
            {"id": 1, "start": 1, "profile": [[b.mean, b.maximum] for b in ref]},
            {"id": 2, "start": 2, "profile": [[b.mean, b.maximum] for b in other]},
        ]
        match = model.predict(ref[:30], model.with_patterns(history))
        self.assertIsNotNone(match)
        self.assertEqual(match.matched_cycle_ids[0], 1)
        self.assertGreaterEqual(match.remaining_seconds, 0)
        self.assertTrue(math.isfinite(match.distance))
        rejected = model.predict([Bin(1000, 1200)] * 35, [{"id": 3, "profile": [[1, 2]] * 120}])
        self.assertIsNone(rejected)

    def test_archive_idempotency_and_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = storage_module.CycleStorage(str(Path(tmp) / 'wash.db'))
            repo.initialize()
            points = [Reading(0, 0), Reading(10, 40), Reading(500, 1600), Reading(900, 0)]
            one = repo.add_cycle(10, 900, points)
            two = repo.add_cycle(10, 900, points)
            self.assertEqual(one, two)
            self.assertTrue(repo.label_cycle(one, 'Cotton 40'))
            rows = repo.list_cycles()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['label'], 'Cotton 40')
            self.assertEqual(len(rows[0]['profile']), 30)

    def test_active_session_is_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'wash.db')
            repo = storage_module.CycleStorage(path)
            repo.initialize()
            repo.save_active(1, [Reading(1, 10), Reading(2, 20)])
            start, items = storage_module.CycleStorage(path).get_active()
            self.assertEqual(start, 1)
            self.assertEqual(items[-1].power, 20)
            repo.clear_active()
            self.assertEqual(repo.get_active(), (None, []))


if __name__ == '__main__':
    unittest.main()
