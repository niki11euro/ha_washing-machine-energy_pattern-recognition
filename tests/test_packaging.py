"""Check requirements for HACS custom repositories without external packages."""

import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = 'washing_machine_energy_pattern_recognition'
INTEGRATION = ROOT / 'custom_components' / DOMAIN


class HacsPackagingTests(unittest.TestCase):
    def test_manifest_and_hacs_versions(self):
        manifest = json.loads((INTEGRATION / 'manifest.json').read_text())
        hacs = json.loads((ROOT / 'hacs.json').read_text())
        self.assertEqual(manifest['domain'], DOMAIN)
        self.assertEqual(manifest['integration_type'], 'device')
        self.assertEqual(manifest['version'], '0.2.1')
        self.assertTrue(manifest['config_flow'])
        self.assertTrue(manifest['version'])
        self.assertTrue(manifest['documentation'].startswith('https://'))
        self.assertTrue(manifest['issue_tracker'].startswith('https://'))
        self.assertEqual(manifest['requirements'], [])
        self.assertEqual(hacs['homeassistant'], '2026.3.0')
        self.assertTrue(hacs['name'])
        self.assertNotIn('render_readme', hacs)

    def test_no_excess_helpers_or_entities(self):
        code = (INTEGRATION / 'sensor.py').read_text()
        self.assertIn('DESCRIPTIONS = {', code)
        self.assertNotIn('\"status\":', code)
        self.assertNotIn('\"confidence\":', code)
        self.assertNotIn('\"count\":', code)
        self.assertNotIn('\"last\":', code)
        self.assertEqual((INTEGRATION / 'binary_sensor.py').read_text().count('class WashingPatternRunning'), 1)

    def test_brand_icons_and_logos(self):
        brand = INTEGRATION / 'brand'
        for file, dimensions in {
            'icon.png': (256, 256),
            'icon@2x.png': (512, 512),
            'logo.png': (840, 240),
            'logo@2x.png': (1680, 480),
            'dark_logo.png': (840, 240),
            'dark_logo@2x.png': (1680, 480),
        }.items():
            with self.subTest(filename=file):
                data = (brand / file).read_bytes()
                self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('>II', data[16:24]), dimensions)

    def test_translations_complete(self):
        strings = json.loads((INTEGRATION / 'strings.json').read_text())
        for lang in ('de', 'en'):
            with self.subTest(language=lang):
                localized = json.loads((INTEGRATION / 'translations' / f'{lang}.json').read_text())
                self.assertEqual(set(localized['entity']['sensor']), {'pattern', 'remaining', 'finish'})
                self.assertEqual(localized['entity']['sensor'].keys(), strings['entity']['sensor'].keys())
                self.assertEqual(localized['entity']['binary_sensor'].keys(), strings['entity']['binary_sensor'].keys())


if __name__ == '__main__':
    unittest.main()
