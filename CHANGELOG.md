# Changelog

## 0.2.0 — 2026-10-14

- Fix Home Assistant integration type from `helper` to `device`, so it appears under normal integrations instead of helpers.
- Reduce the entity count to four meaningful readings per washing machine.
- Retain original unique IDs for the running, pattern, remaining-time, and finish-time entities.
- Move prediction confidence, archive counts, and last-cycle statistics to native entity attributes.
- Use translation keys for English and German entity names.
- Keep all existing cycle history and SQLite files when upgrading from 0.1.x.
- Update HACS upgrade guidance and add regression tests.

## 0.1.1 — 2026-10-14

- Add local icon and light/dark logo assets, HACS and hassfest workflows, and HACS metadata.

## 0.1.0 — 2026-10-14

- Initial local washing cycle detection, SQLite archive, DCT profiling, and DTW matching.
