"""UI entities for profile classification and completion estimates."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


DESCRIPTIONS = {
    "status": ("Status", None, None),
    "pattern": ("Detected pattern", None, None),
    "remaining": ("Estimated remaining time", "min", SensorStateClass.MEASUREMENT),
    "finish": ("Estimated finish", None, None),
    "confidence": ("Prediction confidence", "%", SensorStateClass.MEASUREMENT),
    "count": ("Archived cycles", None, SensorStateClass.TOTAL),
    "last": ("Last completed cycle", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WashingPatternSensor(manager, entry.entry_id, kind) for kind in DESCRIPTIONS])


class WashingPatternSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, manager, entry_id: str, kind: str):
        self.manager = manager
        self.kind = kind
        self._attr_unique_id = f"{entry_id}_{kind}"
        self._attr_name, self._attr_native_unit_of_measurement, self._attr_state_class = DESCRIPTIONS[kind]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=manager.name,
            manufacturer="Washing Machine Energy Pattern Recognition",
            model="Power profile analyzer",
        )
        if kind in ("finish", "last"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        manager = self.manager
        prediction = manager.prediction
        if self.kind == "status":
            return manager.status
        if self.kind == "count":
            return len(manager.cycles)
        if self.kind == "last":
            return datetime.fromtimestamp(manager.cycles[-1]["end"], timezone.utc) if manager.cycles else None
        if self.kind == "pattern":
            return prediction.pattern if prediction else "Unknown"
        if self.kind == "remaining":
            return round(prediction.remaining_seconds / 60) if prediction else None
        if self.kind == "finish":
            return datetime.fromtimestamp(manager.predicted_end, timezone.utc) if manager.predicted_end else None
        if self.kind == "confidence":
            return prediction.confidence if prediction else None
        return None

    @property
    def extra_state_attributes(self):
        if self.kind == "status":
            return {
                "source_sensor": self.manager.entity_id,
                "start": datetime.fromtimestamp(self.manager.active_since, timezone.utc).isoformat()
                if self.manager.active_since else None,
                "watts": self.manager.last_power,
            }
        if self.kind == "last" and self.manager.cycles:
            cycle = self.manager.cycles[-1]
            return {
                "cycle_id": cycle["id"], "label": cycle["label"],
                "pattern": cycle["pattern"], "energy_kwh": round(cycle["energy_kwh"], 3),
                "duration_minutes": round((cycle["end"] - cycle["start"]) / 60),
                "max_w": round(cycle["max_w"]), "raw_samples": cycle["sample_count"],
            }
        if self.kind == "pattern" and self.manager.prediction:
            p = self.manager.prediction
            return {"matched_cycles": list(p.matched_cycle_ids), "dtw_distance": p.distance,
                    "confidence_is_probability": False}
        return None
