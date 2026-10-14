"""One running/idle indicator with optional statistics as attributes."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WashingPatternRunning(manager, entry.entry_id)])


class WashingPatternRunning(BinarySensorEntity):
    """The washing cycle is currently active."""

    _attr_has_entity_name = True
    _attr_translation_key = "running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:washing-machine"

    def __init__(self, manager, entry_id: str):
        self.manager = manager
        # Stable across upgrades.
        self._attr_unique_id = f"{entry_id}_running"
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
    def is_on(self) -> bool:
        return self.manager.active_since is not None

    @property
    def extra_state_attributes(self):
        manager = self.manager
        last = manager.cycles[-1] if manager.cycles else None
        return {
            "source_power_entity": manager.entity_id,
            "power_w": manager.last_power,
            "started_at": (
                datetime.fromtimestamp(manager.active_since, timezone.utc).isoformat()
                if manager.active_since is not None else None
            ),
            "archived_cycles": len(manager.cycles),
            "last_cycle_id": last["id"] if last else None,
            "last_completed_at": (
                datetime.fromtimestamp(last["end"], timezone.utc).isoformat()
                if last else None
            ),
            "last_cycle_duration_minutes": round((last["end"] - last["start"]) / 60)
            if last else None,
            "last_cycle_energy_kwh": round(last["energy_kwh"], 3) if last else None,
            "last_cycle_max_w": round(last["max_w"]) if last else None,
        }
