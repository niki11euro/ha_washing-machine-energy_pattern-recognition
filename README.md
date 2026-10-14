<p align="center">
  <img src="custom_components/washing_machine_energy_pattern_recognition/brand/logo.png" alt="WashPattern" width="620">
</p>

# Washing Machine Energy Pattern Recognition

**WashPattern** is a local, self-learning Home Assistant integration that recognizes washing-machine electricity patterns and estimates how much time remains. Works with **any power sensor** (Shelly, Tasmota, ESPHome, etc.), without an OpenAI account, external server, subscription or cloud connection.

> **Installation:** Initially distributed via **HACS Custom repositories**. This repository has not been submitted to the official HACS default list.

## Install through HACS (custom repository)

Requires **Home Assistant 2026.3.0 or newer** and HACS installed.

1. In Home Assistant open **HACS** → the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/niki11euro/ha_washing-machine-energy_pattern-recognition`.
3. Choose category **Integration**, select **Add**, then open and download WashPattern.
4. **Restart Home Assistant**.
5. Go to **Settings → Devices & services → Add integration**, search for **Washing Machine Energy Pattern Recognition**.
6. Select the **power sensor** of the washing machine (W, mW or kW).

You can also install it manually by copying `custom_components/washing_machine_energy_pattern_recognition/` into your Home Assistant `config/custom_components/` folder and restarting Home Assistant.

**Important:** Do not copy the repository root into `custom_components`; copy only the integration folder. Existing washing-machine automations and Shelly settings are not changed by this integration.

## Features

- Automatic start/finish detection with editable power thresholds and confirmation times.
- Persistent local **SQLite** database of completed cycles, original readings and 30-second profiles.
- Optional one-time or repeated import of recent Home Assistant **Recorder** history (typically 10-day raw retention).
- Compact **DCT** coefficients for describing a washing cycle and constrained **DTW** comparisons to find similar past cycles.
- Rest-time estimates using partial/prefix DTW, updated every five minutes by default, with a heuristic confidence score.
- Auto-clustering into "Pattern 1", "Pattern 2", etc.; users can label a completed cycle with its actual wash-program name.
- Cycle-in-progress recovery across Home Assistant restarts, plus a running binary sensor and dashboard-ready sensors.
- All analysis happens locally. **No network calls** to an AI service or third-party server.

## Entities

| Entity | Meaning |
| --- | --- |
| Running | True while a washing cycle is detected |
| Status | `idle` or `running` |
| Detected pattern | Automatic group or manually assigned program label |
| Estimated remaining time | Minutes; unavailable when a suitable comparison does not exist |
| Estimated finish | Estimated timestamp |
| Prediction confidence | Relative heuristic score (0–100); **not** a calibrated probability |
| Archived cycles | Number of completed cycles in the local archive |
| Last completed cycle | Last finish time; attributes include `cycle_id`, power peak, energy and duration |

Configure thresholds under **Settings → Devices & services → Washing Machine Energy Pattern Recognition → Configure**. Initial defaults: start above 5 W for 20 seconds, finish below 2.5 W for 8 minutes, minimum washing cycle 10 minutes, first prediction after 10 minutes. These are configurable to your machine and should be tested against actual cycle behavior.

## Import past wash cycles

Open **Developer Tools → Actions** and run:

```yaml
action: washing_machine_energy_pattern_recognition.import_history
data:
  days: 7
```

The integration also attempts an idempotent import on startup (default: last seven days). For best results, your power sensor must already be recorded by Home Assistant Recorder. Older hourly long-term statistics cannot reconstruct the original detailed power trace. Cycles detected too near the lookback boundary are not imported.

## Name a recorded cycle

The **Last completed cycle** sensor exposes the `cycle_id` attribute. To label it:

```yaml
action: washing_machine_energy_pattern_recognition.label_cycle
data:
  cycle_id: 3
  label: Cotton 40°C
```

For multiple configured machines, additionally pass their `entry_id` to either action.

## How prediction works

1. Irregular measurements are converted into time-weighted 30-second average/max bins.
2. A discrete cosine transform (DCT) creates a compact numerical fingerprint.
3. DTW compares profile shapes; a partial DTW alignment matches an unfinished cycle to completed cycles.
4. Only sufficiently close matches are used. The median of up to three matched residual durations becomes the prediction.
5. Similar historical cycles are grouped into recurring patterns; naming these manually is optional.

**Limitations:** Wattage alone cannot determine the exact wash temperature, manufacturer program or phase. A few recorded cycles do **not** guarantee an accurate end-time prediction. Confidence is a relative score, not a probability. Sensor gaps or unusually long pauses may affect results. Prediction quality improves when similar programs have been recorded repeatedly.

## Local files, privacy and backups

One SQLite file per configured washer is stored at `<home-assistant-config>/washing_pattern_<entry_id>.db`, *outside* the HACS-updated integration directory. Installation and updates do not overwrite that database. Include these files in Home Assistant backups. Removing the integration does not delete the archive automatically.

WashPattern does not switch your smart plug, alter automations, or transmit household measurements to a third-party service.

## Brand images and HACS validation

- Built-in custom integration branding is included in `custom_components/washing_machine_energy_pattern_recognition/brand/` (256×256 `icon.png`, 512×512 `icon@2x.png`, light and dark logos). On **Home Assistant 2026.3+**, these assets are shown locally on the integration page.
- HACS currently may show an "icon not available" placeholder in its **own** dashboard even though the icon works in Home Assistant. This is an [upstream HACS issue](https://github.com/hacs/integration/issues/5171), not a missing local brand asset.
- GitHub Actions run Python tests, [HACS validation](https://hacs.xyz/docs/publish/action/) and [Home Assistant hassfest](https://github.com/home-assistant/actions#hassfest).
- HACS custom repositories work without publishing a GitHub Release. A release is recommended before submitting to the default HACS store.

For maintainers: the GitHub repository must remain **public**, have an **About description**, **topics** and enabled issues for the HACS publisher checks. See [HACS publisher requirements](https://hacs.xyz/docs/publish/start/) and [integration requirements](https://hacs.xyz/docs/publish/integration/).

## Development

```bash
python -m unittest discover -s tests -v
```

Problems or suggestions? Please use [GitHub Issues](https://github.com/niki11euro/ha_washing-machine-energy_pattern-recognition/issues). Contributions welcome. **MIT license.**
