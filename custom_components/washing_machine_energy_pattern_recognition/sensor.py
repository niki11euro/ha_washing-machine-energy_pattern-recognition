"""Focused user-facing washing-machine sensors (no HA helper entities)."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

# Every entry exposes only these three sensors plus a running binary sensor.
# Statistics, confidence and the last cycle are attributes, not extra entities.
DESCRIPTIONS = {
    "pattern": {"icon": "mdi:chart-line-variant"},
    "remaining": {"icon": "mdi:timer-outline", "unit": "min", "state_class": SensorStateClass.MEASUREMENT},
    "finish": {"icon": "mdi:clock-check-outline", "device_class": SensorDeviceClass.TIMESTAMP},
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Create only the minimum meaningful Home Assistant sensors."""
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WashingPatternSensor(manager, entry.entry_id, kind) for kind in DESCRIPTIONS])


class WashingPatternSensor(SensorEntity):
    """One of three washer attributes shared by the same appliance device."""

    _attr_has_entity_name = True

    def __init__(self, manager, entry_id: str, kind: str):
        self.manager = manager
        self.kind = kind
        desc = DESCRIPTIONS[kind]
        # Preserve the original unique IDs, automations and dashboards.
        self._attr_unique_id = f"{entry_id}_{kind}"
        self._attr_translation_key = kind
        self._attr_icon = desc["icon"]
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_state_class = desc.get("state_class")
        self._attr_device_class = desc.get("device_class")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=manager.name,
            manufacturer="Washing Machine Energy Pattern Recognition",
            model="Local power profile analyzer",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        manager = self.manager
        prediction = manager.prediction if manager.active_since is not None else None
        if self.kind == "pattern":
            return prediction.pattern if prediction else None
        if self.kind == "remaining":
            return round(prediction.remaining_seconds / 60) if prediction else None
        if self.kind == "finish":
            return datetime.fromtimestamp(manager.predicted_end, timezone.utc) if prediction and manager.predicted_end else None
        return None

    @property
    def extra_state_attributes(self):
        manager = self.manager
        prediction = manager.prediction if manager.active_since is not None else None
        if self.kind == "pattern":
            if prediction:
                return {
                    "matched_cycle_ids": list(prediction.matched_cycle_ids),
                    "dtw_distance": prediction.distance,
                }
            last = manager.cycles[-1] if manager.cycles else None
            return {
                "archived_cycles": len(manager.cycles),
                "last_cycle_id": last["id"] if last else None,
                "last_cycle_label": last.get("label") if last else None,
                "last_cycle_pattern": last.get("pattern") if last else None,
            }
        if self.kind in ("remaining", "finish") and prediction:
            return {
                "confidence_score": prediction.confidence,
                "confidence_is_probability": False,
                "matched_cycle_ids": list(prediction.matched_cycle_ids),
                "dtw_distance": prediction.distance,
            }
        return None
