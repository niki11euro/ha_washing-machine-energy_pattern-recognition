# Washing Machine Energy Pattern Recognition

A **local, self-learning Home Assistant custom integration** which recognizes washing-cycle energy patterns from an existing smart-plug power sensor and estimates the time remaining. **No cloud account, AI key, subscription or separate server required.**

## Features

- Select any Home Assistant power sensor (W, mW, kW) in the UI.
- Start and stop detection with adjustable thresholds and dwell times.
- Archive completed cycles independently of Home Assistant Recorder's default retention.
- Automatically import already recorded cycles from the last 1–9 days.
- Store original power readings and 30-second time-weighted profiles in separate SQLite storage.
- Model each cycle with 24 DCT coefficients and label similar historic profiles using constrained DTW.
- Estimate remaining time with partial/prefix DTW, showing a **heuristic** confidence score.
- Restore in-progress sessions after restart; persist raw power data about every 30 seconds.
- Provide dashboard-ready sensors, binary sensor, and `import_history` / `label_cycle` actions.
- Fully offline; standard-library algorithms (no heavy NumPy/SciPy packages).

## Install

### HACS (custom repository)

1. HACS → three-dot menu → **Custom repositories** → paste this GitHub repository URL.
2. Choose **Integration**, add repository and download the integration.
3. Restart Home Assistant.
4. **Settings → Devices & services → Add integration → Washing Machine Energy Pattern Recognition**.
5. Choose the power sensor of your washing-machine smart plug.

### Manual

Copy `custom_components/washing_machine_energy_pattern_recognition` into the same path in your Home Assistant configuration directory, restart HA, and add the integration through **Settings → Devices & services**.

Recommended minimum: Home Assistant 2025.12 or later. Recorder must be enabled for the history backfill feature. Sensor must be included in Recorder's tracked entities.

## Sensors

Each washer exposes a **Running** binary sensor and:

| Sensor | Meaning |
|---|---|
| Status | `idle` / `running` |
| Detected pattern | Auto-cluster `Pattern 1`, ... or manually assigned program label |
| Estimated remaining time | Minutes; unavailable until a sufficiently similar previous cycle exists |
| Estimated finish | Predicted UTC timestamp, displayed locally by HA |
| Prediction confidence | Heuristic 0–100 score **not a probability** |
| Archived cycles | Total count |
| Last completed cycle | Timestamp with duration, energy, peak, ID and label attributes |

Prediction begins after 10 minutes by default and updates every 5 minutes. A prediction is withheld if the best historical match is too different. Early predictions with only one prior sample are inherently uncertain.

## Settings

Under the integration's **Configure** menu you can adjust thresholds (5 W start / 2.5 W end by default), confirmation delays (20 s / 8 min), minimum cycle length (10 min), prediction timing and history import lookback.

**False stop prevention:** low power must persist for eight minutes before a cycle is finalized; the end time itself is the beginning of the confirmed low-power interval. If your washer pauses longer than that during a program, increase the delay.

### History import

On startup, the integration attempts to import complete cycles from the Recorder's past seven days. Repeat manually in **Developer tools → Actions**:

```yaml
action: washing_machine_energy_pattern_recognition.import_history
data:
  days: 7
```

Import is idempotent (cycles with start timestamps within 120 seconds are deduplicated). Recorder usually only has approximately ten days of raw history; this does **not** reconstruct older raw curves from hourly long-term statistics.

### Name a cycle

The **Last completed cycle** sensor exposes `cycle_id`. To assign a program name:

```yaml
action: washing_machine_energy_pattern_recognition.label_cycle
data:
  cycle_id: 3
  label: Cotton 40°C
```

If multiple machines are configured, also supply `entry_id` in service data. Naming isn't required for pattern recognition. Similar cycles receive automatic pattern numbers; manually entered program labels take precedence when selected as nearest neighbour.

## How it works

1. The built-in Recorder is used for historical backfill and for recovery of missing live power changes at cycle completion.
2. Current measurement changes are buffered and persisted in a separate SQLite archive every 30 seconds while running.
3. End-of-cycle raw data is resampled using a time-weighted zero-order hold into 30-second mean/max bins.
4. An orthonormal discrete cosine transform (DCT-II) of log power yields compact coefficients for archival and future experimentation; **DTW still uses the full mean/max profile**, preserving useful peaks.
5. A band-constrained DTW clusters complete cycles. During a cycle, restricted prefix-DTW aligns the current partial trace to each archived reference and takes the median of up to three matched remaining times.
6. If no plausible match exists, the prediction stays unavailable instead of reporting a misleadingly precise time.

**Important:** Electrical power alone cannot reliably identify the exact manufacturer program, temperature or wash phase; pattern names are not machine-program identification without user labeling. The comparison/confidence thresholds are initial heuristics. They should be validated with more real cycles before relying on precise deadlines. In a power outage or HA shutdown, a gap in Recorder data can limit accuracy.

## Storage and privacy

Each configured washer writes `washing_pattern_<config_entry_id>.db` into Home Assistant's configuration directory. It contains full power traces, profiles, coefficient arrays and optional manual labels. **No data leaves Home Assistant.** Include these DB files in backups. Removing the integration does not automatically delete them.

The integration does **not** switch the smart plug or modify existing Home Assistant automations. If you have other automations sending wash-finished notifications, they continue to run independently.

## Development

```bash
python -m unittest discover -s tests -v
```

Issues and contributions welcome. MIT license.
